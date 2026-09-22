# List today's Daily Review / Mohan meetings in Outlook desktop calendar
$py = "C:\Users\LYal01\ZABC\projects\done\small\jira-release-tool\.venv\Scripts\python.exe"
$root = Split-Path -Parent $PSScriptRoot
$env:PYTHONPATH = $root
& $py -c @"
import win32com.client
from datetime import date
outlook = win32com.client.gencache.EnsureDispatch('Outlook.Application')
cal = outlook.GetNamespace('MAPI').GetDefaultFolder(9)
items = cal.Items
items.IncludeRecurrences = True
items.Sort('[Start]')
today = date.today()
for item in items:
    try:
        if item.Class != 26: continue
        if item.Start.date() != today: continue
        s = str(item.Subject or '')
        if 'Daily Review' in s or 'Mohan' in s or 'Quick sync' in s:
            print(f'{item.Start} -> {item.End} | {s}')
    except Exception:
        pass
"@
