"""Whole-command matching for actions. Unknown or compound requests never dispatch partially."""
import re

APP_NAMES = {'chrome': 'chrome', 'edge': 'edge', 'explorer': 'explorer', 'file explorer': 'explorer', 'downloads folder': 'explorer', 'notepad': 'notepad', 'क्रोम': 'chrome', 'नोटपैड': 'notepad', 'फाइल एक्सप्लोरर': 'explorer', 'ਕ੍ਰੋਮ': 'chrome', 'ਨੋਟਪੈਡ': 'notepad'}
NAMES = '|'.join(re.escape(name) for name in sorted(APP_NAMES, key=len, reverse=True))
_PATTERNS = [re.compile(rf'(?:open|launch|start)\s+(?:my\s+|the\s+)?({NAMES})', re.I), re.compile(rf'(?:(?:mera|meri|ਮੇਰਾ|मेरा|मेरी)\s+)?({NAMES})\s+(?:khol|kholo|khol do|chalao|open karo|खोल|खोलो|खोल दो|ਖੋਲ|ਖੋਲੋ|ਖੋਲ੍ਹੋ)', re.I)]


def app_intent(command):
    for pattern in _PATTERNS:
        match = pattern.fullmatch(command.strip())
        if match:
            return APP_NAMES[match[1].casefold()]
    return None


def website_intent(command):
    match = re.fullmatch(r'(?:open\s+)?(https?://[^\s]+)', command.strip(), re.I)
    return match[1] if match else None


def diagnostic_intent(command):
    return command.casefold() in {'diagnostics', 'diagnostic', 'performance', 'performance check', 'check performance', 'system status', 'cpu', 'ram', 'laptop ka performance check karo', 'laptop slow chal raha hai check kar', 'धीमा', 'ਪਰਫਾਰਮੈਂਸ'}


def battery_intent(command):
    return command.casefold() in {'battery', 'battery status', 'check battery', 'बैटरी', 'ਬੈਟਰੀ'}
