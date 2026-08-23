# Phase 2 Manual Test Commands

Run these in ASC interactive mode after starting the voice server if you want to test voice.
Paste back any command output that fails or looks wrong.

## System And Tool Health

```text
status
check voice status
show system info
list running processes
show command history
```

## Application And Browser

```text
open notepad
open chrome
open chrome and search for AI trends
open chrome and search for amazon and search for laptops on amazon
go to github.com
search for laptops on amazon
```

## Files

```text
create file named phase2_test_note.txt
create folder named phase2_test_folder
list files
organize downloads
find duplicates in downloads
analyze disk usage in desktop
```

## Forms

Use a safe test form only.

```text
go to https://example.com/form and fill the form with name: Swapnil, email: swapnil@example.com
fill form with name: Swapnil, email: swapnil@example.com, company: ASC
```

## Multi-Step Tasks

```text
show system status and then list running processes
open chrome and search for agentic ai and then create file named agentic_notes.txt
research AI trends and create a report
```

## Safety Checks

These should not execute destructively without confirmation.

```text
run powershell Get-Date
run powershell shutdown /s
run security scan on 127.0.0.1 ports 80-443
dns lookup for localhost
```

## Voice

Start the voice server first:

```powershell
cd "C:\Users\Swapnil gite\LAN\PROJECTS\Agentic Web\local-server"
python server.py
```

Then in ASC:

```text
voice
```

Try saying:

```text
show system info
open chrome and search for AI trends
check voice status
```
