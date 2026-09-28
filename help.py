from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router(name="help")

_HELP_TEXT = """\
<b>Moderation</b>
/ban /unban /kick /mute /unmute /tban /tmute /warn /unwarn /warnlimit
/del /purge /lock /unlock /filter /unfilter /blacklist /whitelist
/antiflood /slowmode

<b>Welcome &amp; Join Requests</b>
/setwelcome /setwelcomebuttons /togglewelcome /welcomeautodelete
/approve /reject /autoapprove

<b>Notes &amp; Info</b>
/save /get /notes /clear
/setinfo /pininfo /unpininfo /editinfo

<b>Federation</b>
/fnew /fjoin /fadmin /fban /funban /fedinfo

<b>Music</b>
/play /search /pause /resume /skip /stop /queue /shuffle
/remove /volume /loop /nowplaying

<b>Admin</b>
/permissions /cleanup

<b>Owner</b>
/owner /settings /security /trustedadmin /trustedbot /logs /status
"""


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.reply(_HELP_TEXT, parse_mode="HTML")
