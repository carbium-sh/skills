"""Tests for scripts/build-skills.py and the plugin it fills. Run: python3 -m unittest discover -s tests"""

import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "build-skills.py"
SOURCE = ROOT / "source" / "carbium-skill.md"
DCA_SOURCE = ROOT / "source" / "carbium-dca-skill.md"
PLUGIN = ROOT / "plugins" / "carbium"
SKILLS = PLUGIN / "skills"
MAIN = "carbium-solana-api"

spec = importlib.util.spec_from_file_location("build_skills", SCRIPT)
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)
GUIDE = SOURCE.read_text(encoding="utf-8")


def run(out, *sources):
    return subprocess.run([sys.executable, "-I", str(SCRIPT), *map(str, sources), "--out", str(out)],
                          capture_output=True, text=True)


def tree(folder):
    return {str(p.relative_to(folder)): p.read_bytes() for p in sorted(Path(folder).rglob("*")) if p.is_file()}


def build_with(guide=None, before=None, source=SOURCE, **settings):
    """Runs build.build, the function the command line calls, with the guide or module settings
    changed. Returns the BuildError text ("" when the build passes) and the files it wrote."""
    saved = {name: getattr(build, name) for name in settings}
    for name, value in settings.items():
        setattr(build, name, value)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            if guide is not None:
                source = Path(tmp) / "skill.md"
                source.write_text(guide, encoding="utf-8")
            if before:
                before(Path(tmp) / "out" / MAIN)
            try:
                return "", build.build(source, Path(tmp) / "out", rerun=False)[1]
            except build.BuildError as error:
                return str(error), {}
    finally:
        for name, value in saved.items():
            setattr(build, name, value)


def with_main(**change):
    """GUIDES with the main guide's entry changed."""
    return {**build.GUIDES, MAIN: {**build.GUIDES[MAIN], **change}}


def insert(guide, after, lines):
    rows = guide.split("\n")
    at = rows.index(after) + 2
    return "\n".join(rows[:at] + lines + rows[at:])


def changing(path, edit):
    """An assemble() that edits one generated file's lines before they are written."""
    assemble = build.assemble

    def edited(text, runs):
        files = assemble(text, runs)
        edit(files[path])
        return files

    return edited


class Split(unittest.TestCase):
    def test_both_guides_build(self):
        with tempfile.TemporaryDirectory() as out:
            result = run(out, SOURCE, DCA_SOURCE)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("build-skills: carbium-solana-api ok", result.stdout)
        self.assertIn("build-skills: carbium-dca ok", result.stdout)

    def test_two_runs_write_the_same_bytes(self):
        with tempfile.TemporaryDirectory() as one, tempfile.TemporaryDirectory() as two:
            self.assertEqual(run(one, SOURCE, DCA_SOURCE).returncode, 0)
            self.assertEqual(run(two, SOURCE, DCA_SOURCE).returncode, 0)
            self.assertEqual(tree(one), tree(two))

    def test_a_second_run_that_differs_is_caught(self):
        with tempfile.TemporaryDirectory() as one, tempfile.TemporaryDirectory() as two:
            (Path(one) / "SKILL.md").write_text("a\n")
            (Path(two) / "SKILL.md").write_text("b\n")
            self.assertEqual(build.compare(Path(one), Path(two), ["SKILL.md"]),
                             ["SKILL.md: a second run wrote different bytes"])

    def test_a_dropped_line_fails_the_build(self):
        error, _ = build_with(assemble=changing("references/websocket.md", lambda rows: rows.pop(40)))
        self.assertIn("is missing or changed at references/websocket.md", error)

    def test_a_planted_reword_fails_the_build(self):
        def reword(rows):
            n = next(i for i, row in enumerate(rows) if "validator" in row)
            rows[n] = rows[n].replace("validator", "upstream", 1)

        error, _ = build_with(assemble=changing("references/rpc.md", reword))
        self.assertIn("is missing or changed at references/rpc.md", error)

    def test_the_index_stays_under_500_lines(self):
        lines = build_with()[1]["SKILL.md"].count(b"\n")
        error, _ = build_with(insert(GUIDE, "## Read this first", ["- padding"] * (499 - lines)))
        self.assertEqual(error, "")
        error, _ = build_with(insert(GUIDE, "## Read this first", ["- padding"] * (500 - lines)))
        self.assertTrue(error.startswith("carbium-solana-api/SKILL.md: 500 lines"), error)

    def test_an_oversized_reference_fails_the_build(self):
        error, _ = build_with(insert(GUIDE, "## RPC (JSON-RPC 2.0 over HTTPS)", ["x" * 99] * 60))
        self.assertRegex(error, r"references/rpc\.md: 509 lines and 55\d{3} bytes, limit 2000 lines and 55000 bytes")

    def test_the_das_part_has_its_own_file_and_row(self):
        files = build_with()[1]
        self.assertTrue(files["references/das.md"].startswith(b"### DAS: getAsset,"))
        self.assertIn(b"The DAS part of this section is in `references/das.md`.", files["references/rpc.md"])
        self.assertIn(b"| [references/das.md](references/das.md) | Rules; Limits;", files["SKILL.md"])

    def test_a_split_heading_the_guide_lost_fails_the_build(self):
        error, _ = build_with(GUIDES=with_main(splits={"DAS: renamed": "references/das.md"}))
        self.assertIn("splits: 'DAS: renamed' is not one ### heading of the guide", error)

    def test_testing_and_support_go_to_the_index_when_present(self):
        for tail in ("\n## Testing\n\nHow to test.\n", "\n## Testing\n\nHow to test.\n\n## Support\n\nWho to ask.\n"):
            with self.subTest(tail=tail):
                error, files = build_with(GUIDE + tail)
                self.assertEqual(error, "")
                self.assertTrue(files["SKILL.md"].endswith(tail[1:].encode()))

    def test_a_section_the_table_does_not_name_fails_the_build(self):
        tail = "\n## Testing\n\nHow to test.\n\n## Support\n\nWho to ask.\n\n## Benchmarks\n\nNumbers.\n"
        error, _ = build_with(GUIDE + tail)
        self.assertIn("the guide's ## sections differ from its sections in GUIDES", error)

    def test_a_guide_with_no_entry_in_guides_fails_the_build(self):
        error, _ = build_with(GUIDE.replace("name: carbium-solana-api", "name: carbium-other", 1))
        self.assertIn("no entry in GUIDES for the skill 'carbium-other'", error)

    def test_a_stale_file_fails_the_build(self):
        def stale(folder):
            (folder / "references").mkdir(parents=True)
            (folder / "references" / "old.md").write_text("old\n")

        error, _ = build_with(before=stale)
        self.assertIn("references/old.md: not written by this build; remove it", error)

    def test_only_an_unquoted_description_is_quoted(self):
        main = build_with()[1]["SKILL.md"].decode().split("\n")
        guide = GUIDE.split("\n")
        self.assertEqual(main[2], "description: " + json.dumps(guide[2][len("description: "):], ensure_ascii=False))
        self.assertEqual(main[:2] + main[3:4], guide[:2] + guide[3:4])
        dca = build_with(source=DCA_SOURCE)[1]["SKILL.md"].decode().split("\n")
        self.assertEqual(dca[:4], DCA_SOURCE.read_text(encoding="utf-8").split("\n")[:4])

    def test_an_overlong_description_fails_the_build(self):
        rows = GUIDE.split("\n")
        rows[2] = "description: " + "x" * 1025
        error, _ = build_with("\n".join(rows))
        self.assertIn("SKILL.md: description is 1025 characters, limit 1024", error)

    def test_a_contents_entry_off_by_one_fails_the_build(self):
        def shift(rows):
            rows[4] = re.sub(r"line (\d+)$", lambda m: f"line {int(m.group(1)) + 1}", rows[4])

        error, _ = build_with(assemble=changing("references/rpc.md", shift))
        self.assertRegex(error, r"references/rpc\.md: contents entry '- Wire rules \(follow all of them\): line \d+'"
                                r" does not point at its heading")

    def test_a_link_inside_a_reference_fails_the_build(self):
        error, _ = build_with(assemble=changing("references/rpc.md", lambda rows: rows.append("[x](references/das.md)")))
        self.assertIn("a link in a reference resolves from references/; write `references/das.md` as text", error)

    def test_an_index_link_to_a_missing_file_fails_the_build(self):
        def retarget(rows):
            n = next(i for i, row in enumerate(rows) if "[references/rpc.md](references/rpc.md)" in row)
            rows[n] = rows[n].replace("(references/rpc.md)", "(references/rpcs.md)")

        error, _ = build_with(assemble=changing("SKILL.md", retarget))
        self.assertIn("link to references/rpcs.md resolves to no file in the skill", error)

    def test_an_index_link_named_for_a_heading_another_file_holds_fails_the_build(self):
        error, _ = build_with(assemble=changing("SKILL.md", lambda rows: rows.append("[Key states](references/rpc.md)")))
        self.assertIn("'Key states' is not a heading in references/rpc.md", error)


    def test_a_path_to_a_file_the_skill_lacks_fails_the_build(self):
        def misname(rows):
            n = rows.index("The DAS part of this section is in `references/das.md`.")
            rows[n] = "The DAS part of this section is in `references/dass.md`."

        error, _ = build_with(assemble=changing("references/rpc.md", misname))
        self.assertIn("names references/dass.md, which is not a file of the skill", error)

    def test_an_anchor_that_names_no_heading_fails_the_build(self):
        error, _ = build_with(source=DCA_SOURCE,
                              assemble=changing("references/quote.md", lambda rows: rows.append("[x](#no-such-heading)")))
        self.assertIn("carbium-dca/references/quote.md:", error)
        self.assertIn(": #no-such-heading names no heading in the skill", error)

    def test_a_renamed_heading_its_anchors_lose_fails_the_build(self):
        guide = DCA_SOURCE.read_text(encoding="utf-8").replace("\n#### Timing\n", "\n#### Timings\n")
        error, _ = build_with(guide)
        self.assertIn("#timing names no heading in the skill", error)


def headings_of(rows):
    """{slug: line number} of a file's headings outside code fences, by the build's own slug rule:
    lower case, each run of characters that are not letters or digits one hyphen, ends trimmed."""
    found, fenced = {}, False
    for n, row in enumerate(rows, 1):
        if row.lstrip().startswith("```"):
            fenced = not fenced
        elif not fenced and re.match(r"#{1,6} ", row):
            found.setdefault(re.sub(r"[\W_]+", "-", row.split(" ", 1)[1].lower()).strip("-"), n)
    return found


class Navigation(unittest.TestCase):
    def files(self, skill, **settings):
        error, files = build_with(source=DCA_SOURCE if skill == "carbium-dca" else SOURCE, **settings)
        self.assertEqual(error, "")
        return {rel: data.decode().split("\n")[:-1] for rel, data in files.items()}

    def expected_links(self, files):
        """{file: {anchor: the file holding its heading}} for each # link to a heading in another file."""
        homes = {}
        for rel in ["SKILL.md"] + sorted(r for r in files if r != "SKILL.md"):
            for name in headings_of(files[rel]):
                homes.setdefault(name, rel)
        out = {}
        for rel, rows in files.items():
            own = headings_of(rows)
            for name in re.findall(r"\]\(#([^)\s]+)\)", "\n".join(rows)):
                if name not in own:
                    out.setdefault(rel, {})[name] = homes[name]
        return out

    def stated_links(self, files):
        out = {}
        for rel, rows in files.items():
            for row in rows:
                if row.startswith("Links from this file to other files: "):
                    for part in row[len("Links from this file to other files: "):-1].split("; "):
                        names, home = re.match(r"(.+) (?:is|are) in (\S+)$", part).groups()
                        for name in re.findall(r"#([a-z0-9-]+)", names):
                            out.setdefault(rel, {})[name] = home
        return out

    def test_each_link_line_names_exactly_its_cross_file_anchors(self):
        for skill in (MAIN, "carbium-dca"):
            with self.subTest(skill=skill):
                files = self.files(skill)
                self.assertEqual(self.stated_links(files), self.expected_links(files))
        self.assertEqual(sum(map(len, self.expected_links(self.files("carbium-dca")).values())), 28)

    def test_a_moved_heading_moves_its_link_line(self):
        sections = [(t, "references/reading.md" if t == "Read DCAs" else f, r)
                    for t, f, r in build.GUIDES["carbium-dca"]["sections"]]
        files = self.files("carbium-dca", GUIDES={**build.GUIDES, "carbium-dca": {"sections": sections, "splits": {}}})
        self.assertIn("references/reading.md", files)
        self.assertEqual(self.stated_links(files), self.expected_links(files))
        self.assertEqual(self.stated_links(files)["references/check-sign-and-send.md"]["timing"], "references/reading.md")

    def test_the_index_names_the_files_the_guide_code_fetches(self):
        line = 'Files the guide\'s code fetches: `check.mjs` and `example.mjs`, in references/full-example.md under "Full example".'
        self.assertIn(line, self.files("carbium-dca")["SKILL.md"])
        guide = DCA_SOURCE.read_text(encoding="utf-8").replace("/docs/dca/example.mjs", "/docs/dca/demo.mjs")
        error, files = build_with(guide)
        self.assertIn(line.replace("example.mjs", "demo.mjs").encode(), files["SKILL.md"])
        self.assertNotIn(b"Files the guide's code fetches", self.files(MAIN) and build_with()[1]["SKILL.md"])

    def test_every_part_of_a_reference_is_in_its_row(self):
        for skill in (MAIN, "carbium-dca"):
            files = self.files(skill)
            for rel, rows in files.items():
                if rel == "SKILL.md":
                    continue
                with self.subTest(file=f"{skill}/{rel}"):
                    top = len(rows[0]) - len(rows[0].lstrip("#"))
                    parts = [re.sub(r" \(.*", "", row.split(" ", 1)[1]) for n, row in enumerate(rows)
                             if n and re.match(r"#{%d,6} " % (top + 1), row) and (n + 1) in self.contents(rows).values()]
                    row = next(r for r in files["SKILL.md"] if f"| [{rel}]({rel}) |" in r)
                    self.assertEqual(row.rsplit(" | ", 1)[1][:-2].split("; ") if parts else [], parts)

    def contents(self, rows):
        found = {}
        for row in rows[4:]:
            m = re.match(r"^(?:  )*- (.+): line (\d+)$", row)
            if not m:
                break
            found[m.group(1)] = int(m.group(2))
        return found

    def contents_problems(self, files):
        return [f"{rel}: {title} at line {n}" for rel, rows in files.items() if rel != "SKILL.md"
                for title, n in self.contents(rows).items() if not rows[n - 1].endswith(" " + title)]

    def test_contents_numbers_land_on_their_headings(self):
        for skill in (MAIN, "carbium-dca"):
            with self.subTest(skill=skill):
                self.assertEqual(self.contents_problems(self.files(skill)), [])
        files = self.files("carbium-dca")
        rows = files["references/check-sign-and-send.md"]
        n = rows.index(next(r for r in rows if r.startswith("Links from this file")))
        rows.insert(n, "an added line the numbers do not count")
        self.assertNotEqual(self.contents_problems(files), [])


CONTENTS_ITEM = re.compile(r"^(?:  )*- .+: line \d+$")
MARKER = re.compile(r"^The .+ part of this section is in `references/[a-z0-9-]+\.md`\.$")
NAVIGATION = re.compile(r"^(Links from this file to other files|Files the guide's code fetches): .+\.$")


def guide_lines(skill):
    """{file: its lines that come from the guide}: the files as committed, with the front matter and the
    lines the build generates (contents lists, the reference table, a split's pointer line) left out."""
    out = {}
    for path in sorted((SKILLS / skill).rglob("*.md")):
        rel, rows = str(path.relative_to(SKILLS / skill)), path.read_text(encoding="utf-8")[:-1].split("\n")
        if rel == "SKILL.md":
            rows = rows[rows.index("---", 1) + 1:]
            t = rows.index("## Reference files")
            end = rows.index("", t + 4)
            while NAVIGATION.match(rows[end + 1]) and rows[end + 2] == "":
                end += 2
            rows = rows[:t] + rows[end + 1:]
        else:
            k = 4
            while k < len(rows) and CONTENTS_ITEM.match(rows[k]):
                k += 1
            if rows[k] == "" and NAVIGATION.match(rows[k + 1]):
                k += 2
            kept = [rows[0]]
            while k < len(rows):
                if MARKER.match(rows[k]):
                    k += 2 if k + 1 < len(rows) and rows[k + 1] == "" else 1
                    continue
                kept.append(rows[k])
                k += 1
            rows = kept
        out[rel] = rows
    return out


def lands_once(guide, files):
    """Problems unless every body line of the guide is in exactly one file, unchanged, in order, each
    file a run of consecutive guide lines that may jump forward only at a heading."""
    body = guide[:-1].split("\n")
    body = body[body.index("---", 1) + 1:]
    problems = []
    got = Counter(row for rows in files.values() for row in rows)
    want = Counter(body)
    for row in sorted(set(got) | set(want)):
        if got[row] != want[row]:
            problems.append(f"{got[row]} in the files, {want[row]} in the guide: {row[:60]!r}")
    for rel, rows in files.items():
        at = 0 if rel == "SKILL.md" else None  # SKILL.md starts where the body starts; a reference at a heading
        for n, row in enumerate(rows):
            if at is not None and at < len(body) and body[at] == row:
                at += 1
            elif re.match(r"#{1,6} ", row) and row in body[at or 0:]:
                at = body.index(row, at or 0) + 1
            else:
                problems.append(f"{rel}: row {n + 1} {row[:40]!r} does not follow the guide line before it")
                break
    return problems


class WordForWord(unittest.TestCase):
    def test_every_body_line_is_in_one_file_unchanged(self):
        for skill, source in ((MAIN, SOURCE), ("carbium-dca", DCA_SOURCE)):
            with self.subTest(skill=skill):
                self.assertEqual(lands_once(source.read_text(encoding="utf-8"), guide_lines(skill)), [])

    def test_a_planted_reword_is_caught(self):
        files = guide_lines(MAIN)
        n = next(i for i, row in enumerate(files["references/rpc.md"]) if "validator" in row)
        files["references/rpc.md"][n] = files["references/rpc.md"][n].replace("validator", "upstream", 1)
        problems = lands_once(GUIDE, files)
        self.assertTrue(any(p.startswith("0 in the files, 1 in the guide") for p in problems), problems)
        self.assertTrue(any(p.startswith("1 in the files, 0 in the guide") for p in problems), problems)

    def test_a_fence_moved_between_files_is_caught(self):
        files = guide_lines("carbium-dca")
        quote = files["references/quote.md"]
        n = next(i for i, row in enumerate(quote) if row.strip() == "```" and i > 0 and quote[i - 1].strip() != "")
        files["references/read-dcas.md"].append(quote.pop(n))
        self.assertEqual(Counter(r for rows in files.values() for r in rows),
                         Counter(r for rows in guide_lines("carbium-dca").values() for r in rows))
        self.assertNotEqual(lands_once(DCA_SOURCE.read_text(encoding="utf-8"), files), [])

    def test_our_own_text_never_says_validator(self):
        own = [ROOT / "README.md", PLUGIN / "rules" / "carbium.mdc", *ROOT.glob(".*-plugin/marketplace.json"),
               ROOT / ".agents" / "plugins" / "marketplace.json", *PLUGIN.glob(".*-plugin/plugin.json")]
        self.assertEqual(len(own), 8)
        self.assertEqual([p.name for p in own if "validator" in p.read_text(encoding="utf-8").lower()], [])


# Agent Skills format, from https://agentskills.io/specification, plus the two rules Anthropic adds for
# uploaded skills (no XML tags; "anthropic" and "claude" are reserved words in a name).
FIELDS = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}


def scalar(value):
    if value.startswith('"'):
        return json.loads(value)
    if not value or value[0] in "[]{}>|*&!%@`'#,?:-" or ": " in value or " #" in value:
        raise ValueError(f"not a plain YAML scalar: {value[:40]!r}")
    return value


def skill_problems(path):
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n") or "\n---\n" not in text[3:]:
        return ["no front matter"]
    head, body = text[4:].split("\n---\n", 1)
    fields, problems, key = {}, [], None
    for line in head.split("\n"):
        try:
            if line.startswith("  ") and key == "metadata":
                k, v = line[2:].split(": ", 1)
                fields["metadata"][k] = scalar(v)
            elif line.endswith(":") and line[:-1] == "metadata":
                key, fields["metadata"] = "metadata", {}
            else:
                key, value = line.split(": ", 1)
                fields[key] = scalar(value)
        except ValueError as error:
            problems.append(f"front matter line {line[:40]!r}: {error}")
    problems += [f"field {k!r} is not in the spec" for k in sorted(set(fields) - FIELDS)]
    name, description = fields.get("name", ""), fields.get("description", "")
    if not 1 <= len(name) <= 64 or not re.fullmatch(r"[a-z0-9-]+", name) or name[0] == "-" or name[-1] == "-" \
            or "--" in name:
        problems.append(f"name {name!r}: 1-64 of a-z, 0-9 and hyphens, no hyphen at an end, no '--'")
    if name != path.parent.name:
        problems.append(f"name {name!r} is not the folder name {path.parent.name!r}")
    if re.search(r"anthropic|claude", name):
        problems.append(f"name {name!r} holds a reserved word")
    if not 1 <= len(description.strip()) <= 1024 or len(description) > 1024:
        problems.append(f"description: {len(description)} characters, must be 1-1024")
    if re.search(r"<[^>]*>", name + description):
        problems.append("XML tag in name or description")
    if "compatibility" in fields and not 1 <= len(fields["compatibility"]) <= 500:
        problems.append("compatibility: must be 1-500 characters")
    if "metadata" in fields and not all(isinstance(v, str) for v in fields["metadata"].values()):
        problems.append("metadata: values must be strings")
    if text.count("\n") >= 500:
        problems.append(f"SKILL.md has {text.count(chr(10))} lines; keep it under 500")
    for target in re.findall(r"\]\(([^)\s:#]+)\)", body):
        if not (path.parent / target).is_file():
            problems.append(f"link {target} resolves to no file in the skill")
    return problems


class AgentSkillsFormat(unittest.TestCase):
    def test_every_skill_follows_the_spec(self):
        skills = sorted(SKILLS.glob("*/SKILL.md"))
        self.assertEqual([p.parent.name for p in skills], ["carbium-dca", "carbium-solana-api"])
        for path in skills:
            self.assertEqual(skill_problems(path), [], path)

    def test_planted_faults_are_caught(self):
        good = 'name: demo-skill\ndescription: "Does a thing. Use when asked."'
        plants = {
            "uppercase name": good.replace("demo-skill", "Demo-skill"),
            "hyphen at the start": good.replace("demo-skill", "-demo-skill"),
            "double hyphen": good.replace("demo-skill", "demo--skill"),
            "65-character name": good.replace("demo-skill", "d" * 65),
            "reserved word": good.replace("demo-skill", "claude-demo"),
            "empty description": 'name: demo-skill\ndescription: ""',
            "1,025-character description": f'name: demo-skill\ndescription: "{"x" * 1025}"',
            "field not in the spec": good + "\nwhen_to_use: always",
            "unquoted colon": "name: demo-skill\ndescription: Does a thing: well.",
        }
        with tempfile.TemporaryDirectory() as tmp:
            ok = Path(tmp) / "demo-skill" / "SKILL.md"
            ok.parent.mkdir()
            ok.write_text(f"---\n{good}\n---\nBody.\n", encoding="utf-8")
            self.assertEqual(skill_problems(ok), [])
            for fault, head in plants.items():
                with self.subTest(fault=fault):
                    ok.write_text(f"---\n{head}\n---\nBody.\n", encoding="utf-8")
                    self.assertNotEqual(skill_problems(ok), [])


class Manifests(unittest.TestCase):
    def load(self, name):
        return json.loads((ROOT / name).read_text(encoding="utf-8"))

    def test_each_agent_gets_the_same_plugin_and_skills_folder(self):
        for agent in ("claude", "cursor", "codex"):
            with self.subTest(agent=agent):
                manifest = self.load(f"plugins/carbium/.{agent}-plugin/plugin.json")
                self.assertEqual(manifest["name"], "carbium")
                self.assertNotIn("mcpServers", manifest)
        self.assertEqual(self.load("plugins/carbium/.codex-plugin/plugin.json")["skills"], "./skills/")
        claude, cursor = self.load(".claude-plugin/marketplace.json"), self.load(".cursor-plugin/marketplace.json")
        codex = self.load(".agents/plugins/marketplace.json")
        # One version everywhere: Claude Code keeps an install on its cached copy until this string changes.
        versions = {self.load(f"plugins/carbium/.{agent}-plugin/plugin.json").get("version") for agent in ("claude", "cursor", "codex")}
        versions |= {claude["version"], cursor["metadata"]["version"]}
        self.assertEqual(len(versions), 1, versions)
        self.assertRegex(versions.pop(), r"^\d+\.\d+\.\d+$")
        for entry, source in ((claude["plugins"][0], claude["plugins"][0]["source"]),
                              (cursor["plugins"][0], cursor["plugins"][0]["source"]),
                              (codex["plugins"][0], codex["plugins"][0]["source"]["path"])):
            self.assertEqual((entry["name"], source), ("carbium", "./plugins/carbium"))
        self.assertTrue({"installation", "authentication"} <= set(codex["plugins"][0]["policy"]))
        self.assertIn("category", codex["plugins"][0])
        self.assertTrue((PLUGIN / "skills" / "carbium-solana-api" / "SKILL.md").is_file())
        self.assertEqual(sorted(p.name for p in PLUGIN.rglob("*mcp*.json")), [])

    def test_one_description_says_where_each_api_lives(self):
        texts = {f"plugins/carbium/.{agent}-plugin/plugin.json": self.load(f"plugins/carbium/.{agent}-plugin/plugin.json")
                 ["description"] for agent in ("claude", "cursor", "codex")}
        for name in (".claude-plugin/marketplace.json", ".cursor-plugin/marketplace.json"):
            texts[name] = self.load(name)["plugins"][0]["description"]
        self.assertEqual(len(set(texts.values())), 1, texts)
        self.assertIn("webhooks and the account API at carbium.sh, and the DCA API at dex.carbium.io.",
                      texts[".claude-plugin/marketplace.json"])


if __name__ == "__main__":
    unittest.main()
