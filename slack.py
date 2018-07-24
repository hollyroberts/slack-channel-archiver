import datetime
from switches import Switches

class Slack:
    # region CONSTANTS
    SLACK_HTML_ENCODING = {'&amp;': '&',
                           '&lt;': '<',
                           '&gt;': '>'}

    SUBTYPES_CUSTOM = ('me_message',
                       'file_comment',
                       'file_mention',
                       'file_share')

    SUBTYPES_NO_PREFIX = ('pinned_item', )

    ATTACHMENT_FIELDS = ('fields',
                         'subtext',
                         'text',
                         'title',
                         'title_link')

    INDENTATION = "        "  # 8 spaces
    INDENTATION_SHORT = "     "  # 5 spaces
    CHAR_PIPE = '|'
    # endregion

    def __init__(self, user_map: dict, process_threads: bool = False):
        self.user_map = user_map
        self.__last_date = None
        self.__last_user = None
        self.thread_msgs = None
        self.process_channel_threads = process_threads

    def format(self, messages: list):
        pass

    def format_messages(self, messages, process_children=False):
        # Reset last date/user
        self.__last_date = None
        self.__last_user = None

        # Build and return data
        formatted_data = []
        for msg in messages:
            # Do not process thread child messages, they will either be processed by reply_broadcast or the parent message
            if not ('thread_ts' in msg and msg['thread_ts'] != msg['ts']) or process_children:
                formatted_data.append(self.format_message(msg))

        formatted_data = "".join(formatted_data)

        return formatted_data.strip()

    def format_message(self, msg):
        prefix_str = "\n"

        # Get timestamp
        timestamp = msg['ts']
        dt = datetime.datetime.fromtimestamp(float(timestamp))
        date = dt.date()

        # Denote change in date if new date
        if self.__last_date is None or self.__last_date < date:
            prefix_str += "\n -- " + str(date.day) + "/" + str(date.month) + "/" + str(date.year) + " -- \n\n"
            self.__last_date = date

        # Timestamp
        body_str = self.format_timestamp(timestamp)

        # Get subtype and username
        subtype = None
        if 'subtype' in msg:
            subtype = msg['subtype']
        username = self.get_username(msg)

        # If not compact and message is new (and date has not changed), add a newline to the prefix
        if self.__last_user != username and prefix_str == "\n":
            prefix_str = "\n" + prefix_str

        # Do stuff based on the subtype
        if subtype == 'thread_broadcast' and not self.process_channel_threads:
            return ""

        if subtype in Slack.SUBTYPES_NO_PREFIX:
            body_str += self.format_msg_text(msg, include_ampersand=False)
        elif subtype in Slack.SUBTYPES_CUSTOM:
            body_str += self.format_msg_custom_type(msg, subtype, username)
        else:
            # Standard message
            if self.__last_user != username:
                body_str = Slack.INDENTATION + username + ":\n" + body_str

            body_str += self.format_msg_text(msg)

        # If message contains replies, then add them as a thread
        if 'thread_ts' in msg and 'replies' in msg and len(msg['replies']) > 0:
            body_str += "\n\n" + Slack.INDENTATION_SHORT + "T: "
            body_str += self. add_thread_msgs(msg)

        # Update last_user
        self.__last_user = username

        return prefix_str + body_str

    def format_msg_text(self, msg, include_ampersand=True):
        ret_str = ""

        # Plain text
        if 'text' in msg:
            ret_str += Slack.improve_message_text(msg['text'], include_ampersand)

        # Attachments
        ret_str += self.add_attachments(msg)

        return ret_str

    def format_msg_custom_type(self, msg, subtype, username):
        ret = ""

        if subtype == 'me_message':
            if self.__last_user != username:
                ret += username + ": "
            ret += "_" + self.format_msg_text(msg) + "_"

        elif subtype == 'file_comment':
            comment_username = self.get_username(msg['comment'])
            ret += self.format_file_msg(msg, comment_username, "commented on")

            ret += "\n" + Slack.INDENTATION_SHORT + "C: "
            ret += msg['comment']['comment']

        elif subtype == 'file_mention':
            ret += self.format_file_msg(msg, username, "mentioned")

        elif subtype == 'file_share':
            # File can be null, if so then just mention
            if msg['file'] is None:
                return msg['text']

            # Is the user uploading the file or sharing it
            if msg['upload']:
                ret += username + " uploaded a file: " + self.get_file_link(msg)
                if 'initial_comment' in msg['file']:
                    ret += " and commented on it\n"
                    ret += Slack.INDENTATION_SHORT + "C: " + msg['file']['initial_comment']['comment']
            else:
                ret += self.format_file_msg(msg, username, "shared")

        elif subtype == 'reply_broadcast':
            ret += username + " replied to a thread"
            # if 'plain_text' in msg:
            #    ret += ":\n" + export.INDENTATION + self.__improveMsgContents(msg['plain_text'])
            ret += self.add_attachments(msg)

        return ret

    def format_file_msg(self, msg, username, phrase: str):
        file_username = self.get_username(msg['file'])

        if file_username == username:
            return username + " " + phrase + " their file: " + self.get_file_link(msg)
        else:
            return username + " " + phrase + " " + file_username + "'s file: " + self.get_file_link(msg)

    @staticmethod
    def get_file_link(msg):
        ret_str = "<"

        if 'file' in msg:
            file_json = msg['file']

            if 'permalink' in file_json:
                ret_str += file_json['permalink']

            ret_str += "|"

            if 'name' in file_json:
                ret_str += file_json['name']

        ret_str += ">"
        return ret_str

    def format_attachment(self, a):
        body_str = ""
        ret_str = ""

        # Only process attachments that contain at least 1 supported field
        if not any(field in Slack.ATTACHMENT_FIELDS for field in a):
            return body_str

        # Pretext should appear as standard text
        if 'pretext' in a:
            ret_str = self.improve_message_text(a['pretext'])

        # Add title (include link if exists)
        title_str = ""
        if 'title_link' in a:
            title_str = "<" + a['title_link'] + ">"

            if 'title' in a:
                title_str = title_str[:-1] + "|" + a['title'] + ">"
        elif 'title' in a:
            title_str = a['title']

        if title_str != "":
            body_str += self.improve_message_text(title_str)

            # Text isn't required, but it's highly likely
            if 'text' in a:
                body_str += "\n" + Slack.INDENTATION

        # Add text
        if 'text' in a:
            body_str += self.improve_message_text(a['text'])

        # Add fields
        if 'fields' in a:
            # Remove the newline from the text in the attachment
            if body_str.endswith("\n"):
                body_str = body_str[:-1]

            # Combine fields
            fields = a['fields']
            field_str = ""
            for f in fields:
                if 'title' in f:
                    field_str += f['title'] + "\n"

                field_str += f['value'] + "\n\n"
            field_str = field_str.strip()

            # Improve text and add to return string
            field_str = self.improve_message_text(field_str)
            if body_str == "":
                body_str = field_str
            else:
                body_str += "\n\n" + Slack.INDENTATION + field_str

        # Denote the attachment by adding A: inline with the timestamp
        ret_str += "\n" + Slack.INDENTATION_SHORT + "A: " + body_str

        return ret_str

    def add_attachments(self, msg):
        ret_str = ""

        if 'attachments' in msg:
            attachments = msg['attachments']

            for a in attachments:
                ret_str += self.format_attachment(a)

        # Last attachment should not add a newline, this is the easiest way to get rid of it
        if ret_str.endswith("\n"):
            ret_str = ret_str[:-1]

        return ret_str

    @staticmethod
    def improve_message_text(msg: str, include_ampersand=True):
        # TODO Make user and channel mentions readable
        # msg = self.__improveUserMentions(msg, include_ampersand)
        # msg = self.__improveChannelMentions(msg)

        # Replace HTML encoded characters
        for i in Slack.SLACK_HTML_ENCODING:
            msg = msg.replace(i, Slack.SLACK_HTML_ENCODING[i])

        # Improve indentation (use spaces instead of tabs, I expect most people to view the data using a monospaced font)
        # At least this works for notepad and notepad++
        msg = msg.replace("\n", "\n" + Slack.INDENTATION)

        return msg

    def get_username(self, msg):
        # Prefer user over username field, since this is an ID and username can be present but blank
        if 'user' in msg:
            username = msg['user']

            if username == "USLACKBOT":
                return 'Slackbot'
            else:
                return self.user_map[username]

        if 'username' in msg:
            return msg['username']

        return "Unknown"

    def add_thread_msgs(self, parent):
        # Combine messages into array
        thread = []
        for child in parent['replies']:
            child_ts = child['ts']
            child_msg = self.thread_msgs[child_ts]
            thread.append(child_msg)

        # Create a new export object to format the messages for us
        s = Slack(self.user_map)
        s.process_channel_threads = True
        thread_str = s.format_messages(thread, process_children=True)

        # Strip thread_str of leading/trailing whitespace, and add extra indentation
        thread_str = thread_str.strip()
        thread_str = thread_str.replace("\n", "\n" + Slack.INDENTATION_SHORT + Slack.CHAR_PIPE + "  ")

        return thread_str

    @staticmethod
    def format_timestamp(ts, full=False, min_divide_char=':'):
        dt = datetime.datetime.fromtimestamp(float(ts))
        date = dt.date()
        time = dt.time()

        time_str = "["
        if full:
            time_str += date.strftime(Switches.date_mode.value) + " - "

        time_str += str(time.hour).rjust(2, '0') + min_divide_char + str(time.minute).rjust(2, '0') + "] "
        return time_str

    @staticmethod
    def __get_thread_msgs(data):
        msgs = {}

        for msg in data:
            if 'thread_ts' not in msg:
                continue

            # Do not save the parent
            if msg['thread_ts'] != msg['ts']:
                msgs[msg['ts']] = msg

        return msgs