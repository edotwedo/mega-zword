# What an app bot can actually access

The model receives tools from Mega Zword. A prompt or a handoff cannot create
permissions or turn an API model into an existing terminal conversation.

| Mode | Available tools | Scope |
|---|---|---|
| Source review | list_files, read_file, finish | Review folder only; numbered reads and citations required |
| Free-bot coding | list_files, read_file, write_file, replace_in_file, run_tests, finish | The dashboard's working folder |
| Ordinary API chat | Prompt and that tab's recent conversation | Project memory only when selected |
| Native CLI/Hive worker | Whatever that existing client exposes | Must be connected and reachable; a saved name does not prove this |

For a self-review, say: "Audit the Mega Zword application source. Inspect files
using your tools. Cite file and line evidence, state what you actually reviewed,
and suggest prioritized upgrade paths. List any missing tools or access."

Source-review requests automatically use read-only tools. For modifications,
choose **Task options > code with a free bot**. Check the displayed working folder
before asking for edits; this is separate from the installed review source.

API credentials stay in local configuration/environment. Never paste tokens,
passwords, account exports or unrelated private notes into a handoff. The model
does not need credential values to use a backend already configured by the app.

The app's file-tool loop currently has no general shell, browser, Git remote or
Hive MCP tool. Those connections must be implemented/exposed explicitly before
an API bot can use them. Ask it to list its actual tools rather than claim it has
everything. A human/Codex handoff can explain architecture and paths; it cannot
transfer this chat's product-specific tools or private client sessions by prose.
