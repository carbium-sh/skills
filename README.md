# Carbium skills

The `carbium` plugin gives your coding agent two of Carbium's guides as skills, in Claude Code, Cursor and Codex:

- `carbium-solana-api`, from https://carbium.sh/skill.md: RPC, DAS, WebSocket subscriptions, the Carbon gRPC stream
  and quote and swap at services.carbium.sh, and webhooks and the account API at carbium.sh.
- `carbium-dca`, from https://carbium.io/docs/dca/skill.md: the DCA API at dex.carbium.io.

Each skill is its guide word for word, cut at its sections. Its `SKILL.md` holds the opening sections and a table of
the reference files, and every other section is a file under `references/`. The DAS part of the RPC section has a
file of its own.

## Install

Claude Code, from your shell:

```sh
claude plugin marketplace add carbium-sh/skills
claude plugin install carbium@carbium
```

In a session, run `/plugin marketplace add carbium-sh/skills` and then `/plugin install carbium@carbium`.

Cursor: open "Customize" and import this repository with "From GitHub Repository". Cursor reads the repository's
`.cursor-plugin/marketplace.json`. Then install `carbium` and pick a project or user scope. To try it locally, copy
the plugin from a clone of this repository and run "Developer: Reload Window":

```sh
mkdir -p ~/.cursor/plugins/local && cp -r plugins/carbium ~/.cursor/plugins/local/carbium
```

Codex:

```sh
codex plugin marketplace add carbium-sh/skills
```

Then start `codex`, enter `/plugins`, install `carbium` from the Carbium marketplace and open a new session.

Other agents that read `SKILL.md` files, with the `skills` command line:

```sh
npx skills add carbium-sh/skills
```

## Layout

- `plugins/carbium/skills/carbium-solana-api/` and `plugins/carbium/skills/carbium-dca/`: the skills. The build
  writes them; don't edit them by hand.
- `plugins/carbium/.claude-plugin/`, `.cursor-plugin/` and `.codex-plugin/`: one plugin manifest per agent, all on
  the same `skills/` folder.
- `plugins/carbium/rules/carbium.mdc`: a Cursor rule that points to the skills.
- `.claude-plugin/`, `.cursor-plugin/` and `.agents/plugins/`: the marketplace file each agent reads at the
  repository root.
- `source/carbium-skill.md` and `source/carbium-dca-skill.md`: the copies of the guides the skills are built from.
- `scripts/build-skills.py`: the build. `tests/`: its tests.

## Regenerate the skills

When a guide changes, fetch both and rebuild:

```sh
curl -fsS https://carbium.sh/skill.md -o source/carbium-skill.md
curl -fsS https://carbium.io/docs/dca/skill.md -o source/carbium-dca-skill.md
python3 scripts/build-skills.py source/carbium-skill.md source/carbium-dca-skill.md
python3 -m unittest discover -s tests
```

Then raise the patch version in the same commit, the same in every manifest that carries one (the three `plugin.json`
files and the Claude Code and Cursor marketplace files). Claude Code keeps an installed plugin on its cached copy until
that version changes. The tests fail when the versions differ, and CI fails when the skills changed and the version
did not.

The build needs only the standard library of Python 3. It cuts each guide at its `##` headings as its entry in the
`GUIDES` table in the script lists them, and stops on a heading the entry doesn't have. Add one line for it there with
the file it goes to. A section after the reference sections can only go to `SKILL.md`. The one edit the build makes is
to front matter: a description that is not quoted gets double quotes, so it parses as YAML.

The build adds only navigation: the Reference files table in `SKILL.md`, a contents list at the top of each reference
file, a line in each file whose `#` links name headings in other files saying which file holds each one, a line in
`SKILL.md` naming the files the guide's code fetches, and a line where the DAS part was. A `#` link names a heading
that may be in another file of the same skill.

Before it finishes, the build checks that every line of a guide lands in one file unchanged, that every file stays
within its size limit, that every path and link resolves, every `#` link to a heading somewhere in the skill, and that
a second run writes the same bytes. CI rebuilds the skills
from the committed copies and fails if the result differs from what is committed.

## License

MIT
