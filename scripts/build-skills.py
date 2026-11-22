#!/usr/bin/env python3
"""Builds the plugin's agent skills from copies of Carbium's guides, word for word.

Usage: python3 scripts/build-skills.py SOURCE [SOURCE ...] [--out DIR]

Each SOURCE is a copy of a guide (source/carbium-skill.md from https://carbium.sh/skill.md,
source/carbium-dca-skill.md from https://carbium.io/docs/dca/skill.md). DIR defaults to
plugins/carbium/skills. Each guide becomes the skill folder its front matter names: SKILL.md, the index
an agent reads first, and one file per section under references/ (a part listed in its splits gets a file
of its own). Every body line of the guide lands in exactly one file, unchanged. The one edit is to front
matter: a description that is not quoted is double-quoted, so that it parses as YAML. The build adds
only navigation: the Reference files table in SKILL.md, a contents list at the top of each reference,
one line in a file whose # links name headings in other files saying which file holds each, a line in
SKILL.md naming the files the guide's code fetches, and a line where a split part was (the DAS part).
A # link names a heading that may be in another file of the skill. Then the script checks its own work
and exits 1 on any failure: the guide line by line from the files on disk, the size limits, every path
and link resolving (a # link to a heading somewhere in the skill, a link named for a heading landing on
it), and the same bytes from a second run in a fresh interpreter. Standard library only.
"""

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "plugins" / "carbium" / "skills"
INDEX = "SKILL.md"

# Limits as (most lines, most bytes).
# The index: agentskills.io/specification says "Keep your main SKILL.md under 500 lines" and
# "< 5000 tokens recommended"; 20,000 bytes is a hard stop.
# A reference: one default read of Claude Code's Read tool, which stops at 25,000 tokens and 2,000
# lines. Measured with that tool on references/rpc.md before the DAS part moved out: 73,145 bytes read
# as 31,146 tokens, 2.35 bytes a token, so 25,000 tokens hold about 58,700 bytes. 55,000 leaves room
# for denser text.
INDEX_LIMIT = (499, 20_000)
REFERENCE_LIMIT = (2_000, 55_000)
NAME_MAX, DESCRIPTION_MAX = 64, 1024

# Each guide by the skill name in its front matter. sections: its ## sections in order, as (title, the
# file it lands in, required); text above the first ## goes to the index. A heading the list does not
# name, or a required one the guide lacks, fails the build. The reference table sits in the index
# between the sections before the references and those after them, so a section after the reference
# sections can only go to the index. splits: ### parts that leave their section for a file of their
# own, by exact heading; each runs to the next ### or ## heading, and its section's file says where it
# went.
GUIDES = {
    "carbium-solana-api": {
        "sections": [
            ("Acceptable use", INDEX, True),
            ("Read this first", INDEX, True),
            ("Endpoints and auth", INDEX, True),
            ("RPC (JSON-RPC 2.0 over HTTPS)", "references/rpc.md", True),
            ("WebSocket (JSON-RPC 2.0 subscriptions over WSS)", "references/websocket.md", True),
            ("Carbon stream (Yellowstone gRPC)", "references/carbon-stream.md", True),
            ("Webhooks (a signed HTTPS POST per finalized transaction)", "references/webhooks.md", True),
            ("Quote and swap (`quote`, `swap`, `prices`, `health`)", "references/quote-and-swap.md", True),
            ("Cross-plane: key states, credits, limits, retry", "references/cross-plane.md", True),
            ("Account, keys and billing", "references/account-and-billing.md", True),
            ("Account API keys (run the account by API)", "references/account-api-keys.md", True),
            ("Common mistakes", INDEX, True),
            ("Testing", INDEX, False),
            ("Support", INDEX, False),
        ],
        "splits": {
            "DAS: getAsset, getAssets, getAssetBatch, getAssetsByOwner, getAssetsByGroup, getAssetsByCreator,"
            " getAssetsByAuthority, searchAssets, getNftEditions, getTokenAccounts": "references/das.md",
        },
    },
    "carbium-dca": {
        "sections": [
            ("Overview", INDEX, True),
            ("For agents", INDEX, True),
            ("Endpoints", INDEX, True),
            ("Authentication", INDEX, True),
            ("Rate limits", INDEX, True),
            ("Quote", "references/quote.md", True),
            ("Open a DCA", "references/open-a-dca.md", True),
            ("Check, sign and send", "references/check-sign-and-send.md", True),
            ("Read DCAs", "references/read-dcas.md", True),
            ("Change or close a DCA", "references/change-or-close-a-dca.md", True),
            ("Full example", "references/full-example.md", True),
            ("Errors", INDEX, True),
        ],
        "splits": {},
    },
}

# Generated text: the contents list that opens each reference, the line left where a split part was,
# and the index's table of references. None of these may occur in the guide itself.
CONTENTS_HEAD = "Contents, with the line each part starts on in this file:"
ITEM = re.compile(r"^((?:  )*)- (.+): line (\d+)$")
MOVED = "The {name} part of this section is in `{file}`."
MOVED_LINE = re.compile(r"^The .+ part of this section is in `references/[a-z0-9-]+\.md`\.$")
TABLE_HEAD = "## Reference files"
TABLE_INTRO = ("Every other section of the guide is its own file under `references/`. Open the one for the task;"
               " each starts with its contents and the line each part starts on.")
TABLE_COLUMNS = ["| Section | File | Parts |", "|---|---|---|"]

LINKS_HEAD = "Links from this file to other files: "
FETCH_HEAD = "Files the guide's code fetches: "
NAVIGATION = re.compile(r"^(Links from this file to other files|Files the guide's code fetches): .+\.$")
FETCH = re.compile(r"^\s*curl\s+(?:-\w*O\w*\s+)+https://\S+/([\w.-]+\.\w+)\s*$")
ANCHOR = re.compile(r"\]\(#([^)\s]+)\)")
LINK = re.compile(r"\[([^\]]*)\]\(([^)\s]+)\)")
PATH = re.compile(r"(?<![\w/.-])(references/[a-z0-9-]+\.md|SKILL\.md)")
NAME = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
HEADING = re.compile(r"^(#{1,6}) (.+)$")


class BuildError(Exception):
    def __init__(self, problems):
        super().__init__("\n".join(problems))
        self.problems = problems


def headings(lines, prefix):
    """Indexes of lines that start with prefix, outside fenced code blocks."""
    found, fenced = [], False
    for i, line in enumerate(lines):
        if line.lstrip().startswith("```"):
            fenced = not fenced
        elif not fenced and line.startswith(prefix):
            found.append(i)
    return found


def slug(title):
    """A heading's anchor: lower case, each run of characters that are not letters or digits one hyphen,
    the ends trimmed. All 43 anchors of the DCA guide resolve under it; GitHub's own rule (drop such
    characters, spaces to hyphens) misses one: "GET /position/{address}" gives get-positionaddress."""
    return re.sub(r"[\W_]+", "-", title.lower()).strip("-")


def slugs(lines):
    return {slug(HEADING.match(lines[i]).group(2)) for i in headings(lines, "#") if HEADING.match(lines[i])}


def joined(items):
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def depth(line):
    return len(line) - len(line.lstrip("#"))


def key(title):
    """The name a heading goes by in the text: its title up to " (" or ": "."""
    return re.split(r" \(|: ", title)[0]


def short(title):
    return title.split(" (")[0].replace("|", "\\|")


def load(source):
    text = Path(source).read_bytes().decode("utf-8")
    if "\r" in text or not text.endswith("\n"):
        raise BuildError([f"{source}: expected LF line endings and a final newline"])
    lines = text[:-1].split("\n")
    made = [n for n, line in enumerate(lines, 1)
            if line in (CONTENTS_HEAD, TABLE_HEAD) or MOVED_LINE.match(line)]
    if made:
        raise BuildError([f"guide lines {made}: they read as text this build generates"])
    return lines


def front_matter(lines):
    """{field: line index} of the guide's front matter."""
    if lines[0] != "---" or "---" not in lines[1:8]:
        raise BuildError(["guide: no front matter on its first lines"])
    head = range(1, lines[1:8].index("---") + 1)
    fields = {lines[i].split(": ", 1)[0]: i for i in head if ": " in lines[i]}
    if "name" not in fields or "description" not in fields:
        raise BuildError(["guide: its front matter needs a name and a description"])
    return fields


def rewrite(lines):
    """The text each guide line must have in the output: the guide's own, except a front matter
    description that is not quoted, which is double-quoted so the front matter parses as YAML."""
    out, i = list(lines), front_matter(lines)["description"]
    value = lines[i][len("description: "):]
    if not value.startswith('"'):
        out[i] = "description: " + json.dumps(value, ensure_ascii=False)
    return out


def cut(lines, guide):
    """The guide's ## sections against its entry in GUIDES: [(file, first line index, end index)], with
    the text above the first ## as an index part, and each split part as a part of its own."""
    starts = headings(lines, "## ")
    titles = [lines[i][3:] for i in starts]
    named, k = [], 0
    for title, file, required in guide["sections"]:
        if k < len(titles) and titles[k] == title:
            named.append(file)
            k += 1
        elif required:
            k = -1
            break
    if k != len(titles):
        raise BuildError(["the guide's ## sections differ from its sections in GUIDES", f"  guide:  {titles}",
                          f"  GUIDES: {[t for t, _, _ in guide['sections']]}"])
    parts, moved = [(INDEX, 0, starts[0])], []
    for file, start, end in zip(named, starts, starts[1:] + [len(lines)]):
        subs = [start + j for j in headings(lines[start:end], "### ")]
        at = start
        for s in (s for s in subs if lines[s][4:] in guide["splits"]):
            moved.append(lines[s][4:])
            stop = next((x for x in subs if x > s), end)
            parts += [(file, at, s), (guide["splits"][lines[s][4:]], s, stop)]
            at = stop
        parts.append((file, at, end))
    if sorted(moved) != sorted(guide["splits"]):
        raise BuildError([f"splits: {title!r} is not one ### heading of the guide"
                          for title in guide["splits"] if moved.count(title) != 1])
    runs = []
    for file, s, e in parts:
        if s == e:
            continue
        if runs and runs[-1][0] == file and runs[-1][2] == s:
            runs[-1] = (file, runs[-1][1], e)
        else:
            runs.append((file, s, e))
    index_runs = [n for n, (file, _, _) in enumerate(runs) if file == INDEX]
    if index_runs[0] != 0 or len(index_runs) > 2:
        raise BuildError(["GUIDES: the index takes the sections before the references and those after, no others"])
    return runs


def assemble(text, runs):
    """{relative path: [lines]} for the skill folder."""
    bodies, index_runs = {}, []
    for n, (file, s, e) in enumerate(runs):
        if file == INDEX:
            index_runs.append(text[s:e])
            continue
        body = bodies.setdefault(file, [])
        if body:
            last = max(m for m in range(n) if runs[m][0] == file)
            body += [MOVED.format(name=key(text[runs[m][1]].split(" ", 1)[1]), file=runs[m][0])
                     for m in range(last + 1, n)] + [""]
        body += text[s:e]
    index = index_runs[0] + (index_runs[1] if len(index_runs) > 1 else [])
    homes = {}
    for file, body in [(INDEX, index)] + list(bodies.items()):
        for name in sorted(slugs(body)):
            homes.setdefault(name, file)
    order = [INDEX] + list(bodies)

    def links(body):
        """The navigation line for a file whose # links name headings in other files of the skill."""
        own, away = slugs(body), {}
        for line in body:
            for name in ANCHOR.findall(line):
                if name not in own and name in homes and f"#{name}" not in away.setdefault(homes[name], []):
                    away[homes[name]].append(f"#{name}")
        said = [f"{joined(away[f])} {'is' if len(away[f]) == 1 else 'are'} in {f}" for f in order if away.get(f)]
        return [LINKS_HEAD + "; ".join(said) + "."] if said else []

    fetched = {}
    for file, body in bodies.items():
        above = [j for j in headings(body, "#") if HEADING.match(body[j])]
        for j, line in enumerate(body):
            m = FETCH.match(line)
            if m:
                heading = body[max(h for h in above if h < j)].split(" ", 1)[1]
                fetched.setdefault((file, heading), []).append(f"`{m.group(1)}`")
    said = [f'{joined(names)}, in {file} under "{heading}"' for (file, heading), names in fetched.items()]
    navigation = links(index) + ([FETCH_HEAD + "; ".join(said) + "."] if said else [])

    files, rows = {}, []
    for file, body in bodies.items():
        top = depth(body[0])
        subs = [j for j in headings(body, "#") if HEADING.match(body[j]) and depth(body[j]) > top]
        note = links(body)
        block = 3 + len(subs) + 2 * len(note)
        items = [f"{'  ' * (depth(body[j]) - top - 1)}- {body[j].split(' ', 1)[1]}: line {1 + block + j}" for j in subs]
        files[file] = [body[0], "", CONTENTS_HEAD, ""] + items + [x for line in note for x in ("", line)] + body[1:]
        parts = "; ".join(short(body[j].split(" ", 1)[1]) for j in subs)
        rows.append(f"| {short(body[0].split(' ', 1)[1])} | [{file}]({file}) | {parts} |")
    table = [TABLE_HEAD, "", TABLE_INTRO, ""] + TABLE_COLUMNS + rows + [""] + [x for line in navigation for x in (line, "")]
    files[INDEX] = index_runs[0] + table + (index_runs[1] if len(index_runs) > 1 else [])
    return files


def reconstruct(skill_dir, runs):
    """The guide's line stream rebuilt from the files on disk, generated lines removed, so that the
    lossless check does not trust assemble()'s own bookkeeping."""
    problems, segments = [], {}
    for file in dict.fromkeys(file for file, _, _ in runs):
        path = skill_dir / file
        if not path.is_file():
            problems.append(f"{file}: missing")
            continue
        body = path.read_text(encoding="utf-8")[:-1].split("\n")
        if file == INDEX:
            t = body.index(TABLE_HEAD) if TABLE_HEAD in body else -1
            end = t + 6
            while 0 <= t and end < len(body) and body[end].startswith("| "):
                end += 1
            if t < 0 or body[t + 1:t + 6] != ["", TABLE_INTRO, ""] + TABLE_COLUMNS or end >= len(body) or body[end]:
                problems.append(f"{INDEX}: the reference table is not in its generated form")
                continue
            while end + 2 < len(body) and NAVIGATION.match(body[end + 1]) and body[end + 2] == "":
                end += 2
            segments[file] = [body[:t], body[end + 1:]]
            continue
        if body[1:4] != ["", CONTENTS_HEAD, ""]:
            problems.append(f"{file}: no contents list after its heading")
        k = 4
        while k < len(body) and ITEM.match(body[k]):
            k += 1
        if k + 1 < len(body) and body[k] == "" and NAVIGATION.match(body[k + 1]):
            k += 2
        rest, segs, i = [body[0]] + body[k:], [[]], 0
        while i < len(rest):
            if MOVED_LINE.match(rest[i]):
                while i < len(rest) and MOVED_LINE.match(rest[i]):
                    i += 1
                i += i < len(rest) and rest[i] == ""
                segs.append([])
            else:
                segs[-1].append(rest[i])
                i += 1
        segments[file] = segs
    if problems:
        return None, problems
    stream, origin, used = [], [], dict.fromkeys(segments, 0)
    for file, _, _ in runs:
        if used[file] < len(segments[file]):
            stream += segments[file][used[file]]
            origin += [file] * len(segments[file][used[file]])
        used[file] += 1
    for file, n in used.items():
        spare = segments[file][n:]
        if n > len(segments[file]) or any(spare):
            problems.append(f"{file}: its parts on disk do not match the cut ({len(segments[file])} on disk, {n} cut)")
    return (stream, origin), problems


def compare(one, two, wrote):
    """Problems where two builds of the skill differ."""
    return [f"{rel}: a second run wrote different bytes" for rel in wrote
            if not (one / rel).is_file() or (one / rel).read_bytes() != (two / rel).read_bytes()]


def check(expected, skill_dir, wrote, runs):
    problems = []
    on_disk = sorted(str(p.relative_to(skill_dir)) for p in skill_dir.rglob("*") if p.is_file())
    for extra in sorted(set(on_disk) - set(wrote)):
        problems.append(f"{extra}: not written by this build; remove it")

    # Lossless: the guide, line by line, from the files on disk.
    rebuilt, found = reconstruct(skill_dir, runs)
    problems += found
    if rebuilt:
        stream, origin = rebuilt
        for i, want in enumerate(expected):
            if i >= len(stream):
                problems.append(f"guide lines {i + 1}-{len(expected)} are in no output")
                break
            if stream[i] != want:
                problems.append(f"guide line {i + 1} is missing or changed at {origin[i]}: {want[:80]!r}")
                break
        else:
            if len(stream) > len(expected):
                problems.append(f"{len(stream) - len(expected)} output lines come from no guide line")

    texts = {rel: (skill_dir / rel).read_text(encoding="utf-8") for rel in wrote}
    titles = {}
    for rel, text in texts.items():
        lines = text.split("\n")
        titles[rel] = {key(HEADING.match(lines[i]).group(2)) for i in headings(lines, "#") if HEADING.match(lines[i])}
    names = set().union(*titles.values())
    anchors = set().union(*(slugs(text.split("\n")) for text in texts.values()))

    def lands(rel, n, name, target):
        if name in names and target in titles and name not in titles[target]:
            problems.append(f"{rel}:{n}: '{name}' is not a heading in {target}")

    for rel, text in texts.items():
        data = text.encode("utf-8")
        lines = text[:-1].split("\n")
        most_lines, most_bytes = INDEX_LIMIT if rel == INDEX else REFERENCE_LIMIT
        if len(lines) > most_lines or len(data) > most_bytes:
            problems.append(f"{rel}: {len(lines)} lines and {len(data)} bytes, limit {most_lines} lines"
                            f" and {most_bytes} bytes")
        for n, line in enumerate(lines, 1):
            for name, target in LINK.findall(line):
                if target.startswith("#"):
                    if target[1:] not in anchors:
                        problems.append(f"{rel}:{n}: {target} names no heading in the skill")
                    continue
                if re.match(r"[a-z]+:", target):
                    continue
                if rel != INDEX:
                    problems.append(f"{rel}:{n}: a link in a reference resolves from references/; write `{target}` as text")
                elif not (skill_dir / target).is_file():
                    problems.append(f"{rel}:{n}: link to {target} resolves to no file in the skill")
                else:
                    lands(rel, n, name, target)
            for target in PATH.findall(line):
                if not (skill_dir / target).is_file():
                    problems.append(f"{rel}:{n}: names {target}, which is not a file of the skill")
        if rel != INDEX:
            top = depth(lines[0])
            for item in lines[4:]:
                m = ITEM.match(item)
                if not m:
                    break
                n, want = int(m.group(3)), "#" * (top + 1 + len(m.group(1)) // 2) + " " + m.group(2)
                if not 0 < n <= len(lines) or lines[n - 1] != want:
                    problems.append(f"{rel}: contents entry {item!r} does not point at its heading")

    # Front matter: the fields and limits the index relies on (tests/ checks the whole spec).
    head = texts[INDEX].split("\n")
    fields = dict(line.split(": ", 1) for line in head[1:head.index("---", 1)] if ": " in line)
    description = json.loads(fields.get("description", '""'))
    if fields.get("name") != skill_dir.name or not NAME.match(skill_dir.name) or len(skill_dir.name) > NAME_MAX:
        problems.append(f"{INDEX}: name {fields.get('name')!r} must be {skill_dir.name!r}, a-z, 0-9 and single hyphens")
    if not 1 <= len(description) <= DESCRIPTION_MAX:
        problems.append(f"{INDEX}: description is {len(description)} characters, limit {DESCRIPTION_MAX}")
    return problems


def build(source, out, rerun=True):
    """Builds one guide's skill; returns its name, {relative path: bytes} and the count of edited lines."""
    lines = load(source)
    expected = rewrite(lines)
    name = lines[front_matter(lines)["name"]][len("name: "):]
    if name not in GUIDES:
        raise BuildError([f"guide {source}: no entry in GUIDES for the skill {name!r}"])
    runs = cut(lines, GUIDES[name])
    files = assemble(expected, runs)
    skill_dir = Path(out) / name
    for rel, body in files.items():
        path = skill_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(("\n".join(body) + "\n").encode("utf-8"))
    wrote = sorted(files)
    problems = check(expected, skill_dir, wrote, runs)
    if rerun and not problems:
        with tempfile.TemporaryDirectory() as tmp:
            script = str(Path(__file__).resolve())
            run = subprocess.run([sys.executable, "-I", script, str(source), "--out", tmp, "--no-rerun"],
                                 capture_output=True, text=True)
            if run.returncode != 0:
                problems.append("the second run failed: " + run.stderr.strip())
            else:
                problems += compare(Path(tmp) / name, skill_dir, wrote)
    if problems:
        raise BuildError([f"{name}/{problem}" if problem[:1] != " " else problem for problem in problems])
    return name, {rel: (skill_dir / rel).read_bytes() for rel in wrote}, sum(a != b for a, b in zip(lines, expected))


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("sources", nargs="+", metavar="SOURCE", help="a copy of one of Carbium's guides")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="the plugin's skills folder")
    parser.add_argument("--no-rerun", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    failed = False
    for source in args.sources:
        try:
            name, files, edited = build(source, args.out, rerun=not args.no_rerun)
        except BuildError as error:
            for problem in error.problems:
                print(f"build-skills: {problem}", file=sys.stderr)
            failed = True
            continue
        if not args.no_rerun:
            for rel, data in files.items():
                count = data.count(b"\n")
                print(f"{name}/{rel}: {count} lines, {len(data)} bytes")
            print(f"build-skills: {name} ok, every body line of {source} in one file unchanged,"
                  f" front matter lines quoted: {edited}, same bytes on a second run")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
