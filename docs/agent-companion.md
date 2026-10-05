# Agent Companion

Mochi can keep you company while a coding agent works. With **Claude Code** or
OpenAI's **Codex CLI** set up to tell him what they're doing:

- he opens his little laptop and types along while any agent is working, and
  puts it away when they're all done;
- if an agent has been waiting on a permission prompt for more than about ten
  seconds, he waves once (and may say so) so you notice;
- when a run that took a minute or more finishes, he does a small happy bounce.

Quick back-and-forth turns and permission prompts you answer right away stay
invisible. Mochi never wakes up for an agent, stays quiet during a Focus
session, and follows quiet mode and the ambient-reactions setting like his
other reactions.

## What Mochi sees, and what he doesn't

The agents talk to the cloud. Mochi doesn't, and this feature adds no network
access to him.

Each agent's own hook system runs a tiny local command,
`mochi-agent-signal`, at a few lifecycle moments. It sends Mochi exactly two
things:

- one word: `working`, `activity`, `needs_input`, `finished`, or `ended`;
- an opaque 16-character token, a one-way hash of the agent's session id, so
  two agents running at once don't trample each other.

The hook hands the command a JSON payload that includes things like your
prompt, tool commands, file paths, and the agent's replies. The command reads
**only** the session id from it and throws the rest away. Nothing is stored,
logged, or sent anywhere else, and nothing about what you or the agent typed
ever reaches Mochi.

The command talks to Mochi over the desktop session bus, the same channel his
GNOME helper uses. Any program running as you can send Mochi these words too;
the worst it can do is make him open his laptop, wave, or bounce.

## Set up Claude Code

Add these hooks to `~/.claude/settings.json`. If the file already has a
`"hooks"` object, merge these events into it rather than replacing it.

```json
{
  "hooks": {
    "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "\"$HOME/.local/bin/mochi-agent-signal\" working", "async": true}]}],
    "PostToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": "\"$HOME/.local/bin/mochi-agent-signal\" activity", "async": true}]}],
    "PermissionRequest": [{"matcher": "*", "hooks": [{"type": "command", "command": "\"$HOME/.local/bin/mochi-agent-signal\" needs_input", "async": true}]}],
    "Stop": [{"hooks": [{"type": "command", "command": "\"$HOME/.local/bin/mochi-agent-signal\" finished", "async": true}]}],
    "SessionEnd": [{"hooks": [{"type": "command", "command": "\"$HOME/.local/bin/mochi-agent-signal\" ended", "async": true}]}]
  }
}
```

`"async": true` runs each hook in the background, so Claude Code never waits on
Mochi. The full path is used because a hook's `PATH` may not include
`~/.local/bin`.

Claude Code doesn't run a hook when you interrupt a turn with Esc. Mochi
puts the laptop away on your next prompt, or by himself after 15 quiet
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

Codex versions without the `SessionEnd` or `Interrupt` events simply skip
them; Mochi tidies up after 15 quiet minutes instead.

## Turn it off

Remove the hooks from `~/.claude/settings.json` or `~/.codex/hooks.json`.
Mochi has no separate switch, and he never edits those files himself. Quiet
mode and turning ambient reactions off silence his waves, bounces, and lines,
but not the laptop.

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
3. **Does Mochi react?** Pretend to be an agent:

   ```bash
   echo '{"session_id": "test"}' | ~/.local/bin/mochi-agent-signal working
   # Mochi opens his laptop within about a second
   echo '{"session_id": "test"}' | ~/.local/bin/mochi-agent-signal ended
   # ...and puts it away
   ```

   The command never prints anything, even on failure, because hook output can
   end up in the agent's context. Silence is normal.
4. **Codex does nothing?** Check `/hooks` in Codex and trust the Mochi hooks.
5. **Mochi doesn't wave or bounce?** That's by design while he's asleep, during
   Focus, with quiet mode or ambient reactions off, or while you're dragging
   him or have a menu open. He also skips a wave if you're in the terminal
   where the prompt is, since he only shows it once he's standing idle.
