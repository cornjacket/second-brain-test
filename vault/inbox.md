# Inbox — messages for the next session

**Leave a message here and the next agent session in this brain picks it up.** Append one
line under *Messages*, from any editor, Obsidian, or a phone with git — then commit. Use it
for anything you want done or looked at that you do not want to do right now: "file this
article as a note", "the CSET date moved to March", "check whether the permit email came".

## How it is handled

Every session reads this file first. For each message, the agent either **does it** (if it is
small), or **turns it into something that lasts** — a note, a checkbox in the project note
that owns it, a dashboard row — and then **deletes the line in the same commit**.

This is a **queue, not a log.** A handled message is removed, not ticked: git history keeps the
record, and a list of done items is noise the next session has to read past. A message that
cannot be handled yet stays, with a short reason appended, so it is not silently retried.

## Why this file is not a note

It sits at the vault root, outside every PARA root, like the dashboard — so it is never
embedded and never returned by search. A message is an instruction, not knowledge: once
handled it is gone, and a vector of "do X tomorrow" would compete against your real notes.

## Messages

<!-- One line per message, newest at the bottom:  - YYYY-MM-DD: what you want done -->
