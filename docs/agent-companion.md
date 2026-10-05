# Agent Companion

Mochi can keep you company while a coding agent works. With **Claude Code** or
OpenAI's **Codex CLI** set up to tell him what they're doing:

- while any agent is working, he settles in with his mug beside a little
  monitor that scrolls code, and puts it away when they're all done (in a
  terminal, his laptop gives way to the monitor once a turn runs longer than a
  few seconds);
- if an agent is stuck waiting for you to answer a permission prompt, he waves
  once (and may say so) so you notice;
- when a run that took a minute or more finishes, he does a small happy bounce.

Quick back-and-forth turns stay quiet, and so do permission prompts you answer
right away. Mochi never wakes up for an agent, stays quiet during a Focus
session, and follows quiet mode and the ambient-reactions setting like his
other reactions.

## What Mochi sees, and what he doesn't

The agents talk to the cloud. Mochi doesn't, and this feature adds no network
access to him.

Each agent's own hook system runs a tiny local command,
`mochi-agent-signal`, at a few lifecycle moments. It sends Mochi exactly two
things:

- one word: `working`, `activity`, `needs_input`, `prompt_waiting`,
  `finished`, or `ended`;
- an opaque 16-character token, a one-way hash of the agent's session id, so
  two agents running at once don't trample each other.

The hook hands the command a JSON payload that includes things like your
prompt, tool commands, file paths, and the agent's replies. The command reads
**only** the session id from it and throws the rest away. Nothing is stored,
logged, or sent anywhere else, and nothing about what you or the agent typed
ever reaches Mochi.

The command talks to Mochi over the desktop session bus, the same channel his
GNOME helper uses. Any program running as you can send Mochi these words too;
the worst it can do is make him bring out his monitor, wave, or bounce.

## Set up Claude Code

Add these hooks to `~/.claude/settings.json`. If the file already has a
`"hooks"` object, merge these events into it rather than replacing it.

```json
{
  "hooks": {
    "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "\"$HOME/.local/bin/mochi-agent-signal\" working", "async": true}]}],
    "PostToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": "\"$HOME/.local/bin/mochi-agent-signal\" activity", "async": true}]}],
    "Notification": [{"matcher": "permission_prompt", "hooks": [{"type": "command", "command": "\"$HOME/.local/bin/mochi-agent-signal\" prompt_waiting", "async": true}]}],
    "Stop": [{"hooks": [{"type": "command", "command": "\"$HOME/.local/bin/mochi-agent-signal\" finished", "async": true}]}],
    "SessionEnd": [{"hooks": [{"type": "command", "command": "\"$HOME/.local/bin/mochi-agent-signal\" ended", "async": true}]}]
  }
}
```

- `"async": true` runs each hook in the background, so Claude Code never waits
  on Mochi.
- The `permission_prompt` notification only fires when a permission prompt is
  still unanswered after about six seconds, so a prompt you answer right away
  never makes Mochi wave, even if the command you approved runs for minutes.
- The full path is used because a hook's `PATH` may not include
  `~/.local/bin`.

**Set this up before?** Earlier versions of this page used a
`PermissionRequest` hook with `needs_input`. Replace that entry with the
`Notification` one above.

Claude Code doesn't run a hook when you interrupt a turn with Esc. Mochi puts
the monitor away when your next turn finishes, or by himself after 15 quiet
minutes.

## Set up Codex

Codex 0.124 and newer run hooks out of the box. Add these to
`~/.codex/hooks.json` (again, merge into an existing `"hooks"` object):

```json
{
  "hooks": {
    "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "\"$HOME/.local/bin/mochi-agent-signal\" working --source codex", "async": true}]}],
    "PostToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": "\"$HOME/.local/bin/mochi-agent-signal\" activity --source codex", "async": true}]}],
    "PermissionRequest": [{"matcher": "*", "hooks": [{"type": "command", "command": "\"$HOME/.local/bin/mochi-agent-signal\" needs_input --source codex", "async": true}]}],
    "Stop": [{"hooks": [{"type": "command", "command": "\"$HOME/.local/bin/mochi-agent-signal\" finished --source codex", "async": true}]}],
    "SessionEnd": [{"hooks": [{"type": "command", "command": "\"$HOME/.local/bin/mochi-agent-signal\" ended --source codex", "timeout": 3}]}],
    "Interrupt": [{"hooks": [{"type": "command", "command": "\"$HOME/.local/bin/mochi-agent-signal\" ended --source codex", "timeout": 3}]}]
  }
}
```

**Then trust the hooks.** Codex runs your hooks only after you approve them:
open `/hooks` in Codex and trust each one. Editing a hook later means trusting
it again. Untrusted hooks are the most common reason nothing happens.

Codex has no "still waiting" signal, so Mochi gives each permission prompt 45
seconds before waving. Codex only reports back once an approved command
finishes, so a command you approve that then runs for more than 45 seconds can
still get a wave it didn't need.

Codex versions without the `SessionEnd` or `Interrupt` events simply skip
them; Mochi tidies up after 15 quiet minutes instead.

## Using an agent inside VS Code

While VS Code is focused, Mochi does his usual VS Code coworking instead of
the agent scene, and a wave waits until he's standing idle. Switch to another
window and the monitor comes back while the agent keeps working.

## Turn it off

Remove the hooks from `~/.claude/settings.json` or `~/.codex/hooks.json`.
Mochi has no separate switch, and he never edits those files himself. Quiet
mode and turning ambient reactions off silence his waves, bounces, and lines,
but not the monitor.

Uninstalling Mochi? Remove the hooks first. Otherwise every hook reports
"No such file or directory" once `mochi-agent-signal` is gone.

## Troubleshooting

1. **Is the command installed?** `ls ~/.local/bin/mochi-agent-signal`. If it's
   missing, update or reinstall Mochi.
2. **Can it reach Mochi?** With Mochi running:

   ```bash
   gdbus call --session --dest io.github.mochi_desktop.Mochi \
     --object-path /io/github/mochi_desktop/Mochi \
     --method org.gtk.Actions.List
   ```

   The list should include `agent-event`.
3. **Does Mochi react?** Pretend to be an agent. If his GNOME helper is
   installed, Mochi already has his laptop out while a terminal is focused, so
   run this and then click on a non-terminal window within three seconds:

   ```bash
   sleep 3; echo '{"session_id": "test"}' | ~/.local/bin/mochi-agent-signal working
   # Mochi brings out his monitor within about a second
   sleep 10; echo '{"session_id": "test"}' | ~/.local/bin/mochi-agent-signal ended
   # ...and puts it away
   ```

   The command never prints anything, even on failure, because hook output can
   end up in the agent's context. Silence is normal.
4. **Codex does nothing?** Check `/hooks` in Codex and trust the Mochi hooks.
5. **Mochi doesn't wave or bounce?** That's by design while he's asleep, during
   Focus, with quiet mode or ambient reactions off, or while you're dragging
   him or have a menu open. He also skips a wave while he's busy at a laptop or monitor
   (for example while you're in a terminal or VS Code), since he only shows it
   once he's standing idle.
