# SCP-079-LONG - Control super long messages
# Copyright (C) 2019 SCP-079 <https://scp-079.org>
#
# This file is part of SCP-079-LONG.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import logging

from telegram import Update
from telegram.ext import CallbackContext, Dispatcher, Filters, MessageHandler

from .. import glovar
from ..functions.channel import get_debug_text
from ..functions.etc import code, thread, user_mention
from ..functions.file import save
from ..functions.filters import class_c, class_d, class_e, declared_message, exchange_channel, hide_channel
from ..functions.filters import is_long_text, new_group, test_group
from ..functions.group import leave_group
from ..functions.ids import init_group_id
from ..functions.receive import receive_add_bad, receive_add_except, receive_config_commit, receive_config_reply
from ..functions.receive import receive_declared_message, receive_leave_approve
from ..functions.receive import receive_regex, receive_remove_bad, receive_remove_except, receive_remove_watch
from ..functions.receive import receive_text_data, receive_user_score, receive_watch_user
from ..functions.telegram import get_admins, send_message
from ..functions.tests import long_test
from ..functions.user import terminate_user

# Enable logging
logger = logging.getLogger(__name__)


def add_message_handlers(dispatcher: Dispatcher) -> bool:
    # Add message handlers
    try:
        # Check
        dispatcher.add_handler(MessageHandler(
            filters=(Filters.update.messages & Filters.group & ~test_group & ~class_c & ~class_d & ~class_e
                     & ~declared_message),
            callback=check
        ))
        # Exchange emergency
        dispatcher.add_handler(MessageHandler(
            filters=Filters.update.channel_posts & hide_channel,
            callback=exchange_emergency
        ))
        # Init group
        dispatcher.add_handler(MessageHandler(
            filters=Filters.group & ~test_group & (Filters.status_update.new_chat_members
                                                   | Filters.status_update.chat_created) & new_group,
            callback=init_group
        ))
        # Process data
        dispatcher.add_handler(MessageHandler(
            filters=Filters.update.channel_posts & exchange_channel,
            callback=process_data
        ))
        # Test
        dispatcher.add_handler(MessageHandler(
            filters=Filters.update.messages & Filters.group & test_group,
            callback=test
        ))

        return True
    except Exception as e:
        logger.warning(f"Add message handlers error: {e}", exc_info=True)

    return False


def check(update: Update, context: CallbackContext) -> bool:
    # Check the messages sent from groups
    try:
        client = context.bot
        message = update.edited_message or update.message
        if not message:
            return False

        if is_long_text(message):
            terminate_user(client, message)

        return True
    except Exception as e:
        logger.warning(f"Check error: {e}", exc_info=True)

    return False


def exchange_emergency(update: Update, _: CallbackContext) -> bool:
    # Sent emergency channel transfer request
    try:
        message = update.edited_message or update.message
        if not message:
            return False

        # Read basic information
        data = receive_text_data(message)
        if data:
            sender = data["from"]
            receivers = data["to"]
            action = data["action"]
            action_type = data["type"]
            data = data["data"]
            if "EMERGENCY" in receivers:
                if action == "backup":
                    if action_type == "hide":
                        if data is True:
                            glovar.should_hide = data
                        elif data is False and sender == "MANAGE":
                            glovar.should_hide = data

        return True
    except Exception as e:
        logger.warning(f"Exchange emergency error: {e}", exc_info=True)

    return False


def init_group(update: Update, context: CallbackContext) -> bool:
    # Initiate new groups
    try:
        client = context.bot
        message = update.edited_message or update.message
        if not message:
            return False

        gid = message.chat.id
        text = get_debug_text(client, message.chat)
        invited_by = message.from_user.id
        # Check permission
        if invited_by == glovar.user_id:
            # Remove the left status
            if gid in glovar.left_group_ids:
                glovar.left_group_ids.discard(gid)

            # Update group's admin list
            if init_group_id(gid):
                admin_members = get_admins(client, gid)
                if admin_members:
                    glovar.admin_ids[gid] = {admin.user.id for admin in admin_members
                                             if not admin.user.is_bot}
                    save("admin_ids")
                    text += f"状态：{code('已加入群组')}\n"
                else:
                    thread(leave_group, (client, gid))
                    text += (f"状态：{code('已退出群组')}\n"
                             f"原因：{code('获取管理员列表失败')}\n")
        else:
            if gid in glovar.left_group_ids:
                return leave_group(client, gid)

            leave_group(client, gid)
            text += (f"状态：{code('已退出群组')}\n"
                     f"原因：{code('未授权使用')}\n"
                     f"邀请人：{user_mention(invited_by)}\n")

        thread(send_message, (client, glovar.debug_channel_id, text))

        return True
    except Exception as e:
        logger.warning(f"Init group error: {e}", exc_info=True)

    return False


def process_data(update: Update, context: CallbackContext) -> bool:
    # Process the data in exchange channel
    try:
        client = context.bot
        message = update.edited_message or update.message
        if not message:
            return False

        data = receive_text_data(message)
        if data:
            sender = data["from"]
            receivers = data["to"]
            action = data["action"]
            action_type = data["type"]
            data = data["data"]
            # This will look awkward,
            # seems like it can be simplified,
            # but this is to ensure that the permissions are clear,
            # so it is intentionally written like this
            if glovar.sender in receivers:

                if sender == "CAPTCHA":

                    if action == "update":
                        if action_type == "score":
                            receive_user_score(sender, data)

                elif sender == "CLEAN":

                    if action == "add":
                        if action_type == "bad":
                            receive_add_bad(sender, data)
                        elif action_type == "watch":
                            receive_watch_user(data)

                    elif action == "update":
                        if action_type == "declare":
                            receive_declared_message(data)
                        elif action_type == "score":
                            receive_user_score(sender, data)

                elif sender == "CONFIG":

                    if action == "config":
                        if action_type == "commit":
                            receive_config_commit(data)
                        elif action_type == "reply":
                            receive_config_reply(client, data)

                elif sender == "LANG":

                    if action == "add":
                        if action_type == "bad":
                            receive_add_bad(sender, data)
                        elif action_type == "watch":
                            receive_watch_user(data)

                    elif action == "update":
                        if action_type == "declare":
                            receive_declared_message(data)
                        elif action_type == "score":
                            receive_user_score(sender, data)

                elif sender == "LONG":

                    if action == "add":
                        if action_type == "bad":
                            receive_add_bad(sender, data)
                        elif action_type == "watch":
                            receive_watch_user(data)

                    elif action == "update":
                        if action_type == "declare":
                            receive_declared_message(data)
                        elif action_type == "score":
                            receive_user_score(sender, data)

                elif sender == "MANAGE":

                    if action == "add":
                        if action_type == "bad":
                            receive_add_bad(sender, data)
                        elif action_type == "except":
                            receive_add_except(data)

                    elif action == "leave":
                        if action_type == "approve":
                            receive_leave_approve(client, data)

                    elif action == "remove":
                        if action_type == "bad":
                            receive_remove_bad(sender, data)
                        elif action_type == "except":
                            receive_remove_except(data)
                        elif action_type == "watch":
                            receive_remove_watch(data)

                elif sender == "NOFLOOD":

                    if action == "add":
                        if action_type == "bad":
                            receive_add_bad(sender, data)
                        elif action_type == "watch":
                            receive_watch_user(data)

                    elif action == "update":
                        if action_type == "declare":
                            receive_declared_message(data)
                        elif action_type == "score":
                            receive_user_score(sender, data)

                elif sender == "NOSPAM":

                    if action == "add":
                        if action_type == "bad":
                            receive_add_bad(sender, data)
                        elif action_type == "watch":
                            receive_watch_user(data)

                    elif action == "update":
                        if action_type == "declare":
                            receive_declared_message(data)
                        elif action_type == "score":
                            receive_user_score(sender, data)

                elif sender == "RECHECK":

                    if action == "add":
                        if action_type == "bad":
                            receive_add_bad(sender, data)
                        elif action_type == "watch":
                            receive_watch_user(data)

                    elif action == "update":
                        if action_type == "declare":
                            receive_declared_message(data)
                        elif action_type == "score":
                            receive_user_score(sender, data)

                elif sender == "REGEX":

                    if action == "update":
                        if action_type == "download":
                            receive_regex(client, message, data)

                elif sender == "USER":

                    if action == "remove":
                        if action_type == "bad":
                            receive_remove_bad(sender, data)

                elif sender == "WARN":

                    if action == "update":
                        if action_type == "score":
                            receive_user_score(sender, data)

                elif sender == "WATCH":

                    if action == "add":
                        if action_type == "watch":
                            receive_watch_user(data)

        return True
    except Exception as e:
        logger.warning(f"Process data error: {e}", exc_info=True)

    return False


def test(update: Update, context: CallbackContext) -> bool:
    # Show test results in TEST group
    try:
        client = context.bot
        message = update.edited_message or update.message
        if not message:
            return False

        long_test(client, message)

        return True
    except Exception as e:
        logger.warning(f"Test error: {e}", exc_info=True)

    return False