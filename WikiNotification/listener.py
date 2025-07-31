# -*- coding: utf-8 -*-
# vim: sw=4 ts=4 fenc=utf-8
# =============================================================================
# $Id: listener.py 24 2007-10-26 15:58:00Z s0undt3ch $
# =============================================================================
#             $URL: http://wikinotification.ufsoft.org/svn/trunk/WikiNotification/listener.py $
# $LastChangedDate: 2007-10-26 16:58:00 +0100 (Fri, 26 Oct 2007) $
#             $Rev: 24 $
#   $LastChangedBy: s0undt3ch $
# =============================================================================
# Copyright (C) 2006 UfSoft.org - Pedro Algarvio <ufs@ufsoft.org>
#
# Please view LICENSE for additional licensing information.
# =============================================================================
from email.mime.text import MIMEText
import inspect
from trac.core import *
from trac.notification.api import IEmailDecorator, INotificationFormatter, NotificationEvent, NotificationSystem
from trac.notification.mail import RecipientMatcher, set_header
from trac.perm import PermissionSystem
from trac.resource import Resource
from trac.util.text import exception_to_unicode
from trac.util.translation import deactivate, reactivate
from trac.versioncontrol.diff import unified_diff
from trac.web.chrome import Chrome
from trac.wiki.api import IWikiChangeListener
from trac.wiki.model import WikiPage


diff_header = """Index: {name}
=========================================================================
--- {name} (version: {oldversion})
+++ {name} (version: {version})
"""


class WikiNotificationError(TracError):
    pass


class WikiNotificationChangeEvent(NotificationEvent):
    realm = 'wiki'

    def __init__(self, category, page, time, author,
                 version=None, comment=None,
                 old_name=None, old_comment=None, redirect=False):
        super(WikiNotificationChangeEvent, self).__init__(self.realm, category, page, time, author)
        self.version = version
        self.comment = comment
        self.old_name = old_name
        self.old_comment = old_comment
        self.redirect = redirect


class WikiNotificationChangeListener(Component):
    """Class that listens for wiki changes.
    """

    implements(IWikiChangeListener)

    # IWikiChangeListener methods

    def wiki_page_added(self, page):
        version, time, author, comment = page.get_history().next()
        self._send_notification('added', page, version, time, comment, author)

    def wiki_page_changed(self, page, version, time, comment, author):
        self._send_notification('changed', page, version, time, comment, author)

    def wiki_page_deleted(self, page):
        req = self._get_req()
        author = req and req.authname or 'trac'
        self._send_notification('deleted', page, None, None, None, author)

    def wiki_page_version_deleted(self, page):
        req = self._get_req()
        author = req and req.authname or 'trac'
        version, _time, _author, _comment = page.get_history().next()
        self._send_notification('version deleted', page, version+1, None, None, author)

    def wiki_page_renamed(self, page, old_name):
        req = self._get_req()
        author = req and req.authname or 'trac'
        redirect = req and req.args.get('redirect') or None
        self._watch_renamed_page(page.name, old_name)
        self._send_notification('renamed', page, None, None, None, author, old_name=old_name, redirect=redirect)

    def wiki_page_comment_modified(self, page, old_comment):
        req = self._get_req()
        author = req and req.authname or 'trac'
        self._send_notification('comment modified', page, None, None, None, author, old_comment=old_comment)

    # Internal Methods

    def _get_req(self):
        """Grab req from the stack.
        """
        frame = inspect.currentframe()
        try:
            while frame.f_back:
                frame = frame.f_back
                request = frame.f_locals.get('req')
                if request:
                    self.env.log.debug(request)
                    return request
        finally:
            del frame
        return None

    def _send_notification(self, category, page, version, time, comment, author,
                           old_name=None, old_comment=None, redirect=False):
        event = WikiNotificationChangeEvent(category, page, time, author,
                                            version=version, comment=comment,
                                            old_name=old_name, old_comment=old_comment,
                                            redirect=redirect)
        subscriptions = self._subscriptions(event)
        try:
            NotificationSystem(self.env).distribute_event(event, subscriptions)
        except Exception as e:
            self.log.error("Failure sending notification for '%s' for page "
                           "%s: %s", category, page.name,
                           exception_to_unicode(e))
            raise WikiNotificationError(e)

    def _subscriptions(self, event):
        QUERY_SIDS = """SELECT sid from session_attribute
                        WHERE name=%s AND value LIKE %s"""
        transport_and_format = ('email', 'text/plain')
        matcher = RecipientMatcher(self.env)
        page = event.target
        notify_author = self.config.getbool('wiki-notification', 'notify_author')
        blacklist = self.config.getlist('wiki-notification', 'banned_addresses')
        with self.env.db_query as db:
            cursor = db.cursor()
            cursor.execute(QUERY_SIDS, ('watched_pages', '%,' + page.name + ',%'))
            sids = cursor.fetchall()
            self.log.debug("SIDs to notify: %s", sids)
            perm = PermissionSystem(self.env)
            resource = Resource('wiki', page.name)
            for sid in sids:
                if sid[0] == event.author and not notify_author:
                    self.log.debug('Skipping notification of sid="%s"; notify_author=False.', sid[0])
                    continue
                if not perm.check_permission(action='WIKI_VIEW', username=sid[0], resource=resource):
                    self.log.debug('Skipping notification of sid="%s"; permission denied.', sid[0])
                    continue
                self.log.debug('Notifying sid="%s".', sid[0])
                recipient = matcher.match_recipient(sid[0])
                if recipient:
                    self.log.debug('recipient = %s', recipient)
                    if recipient[2] in blacklist:
                        self.log.debug('Skipping notification of sid="%s"; email "%s" is blacklisted.', sid[0], recipient[2])
                        continue
                    yield recipient + transport_and_format

    def _watch_renamed_page(self, pagename, old_pagename):
        with self.env.db_transaction as db:
            cursor = db.cursor()
            cursor.execute("UPDATE session_attribute SET value=value || %s WHERE name=%s AND value LIKE %s AND value NOT LIKE %s",
                           ('%s,' % pagename, 'watched_pages', '%,' + old_pagename + ',%', '%,' + pagename + ',%'))


class WikiNotificationNotificationFormatter(Component):
    implements(IEmailDecorator, INotificationFormatter)

    realm = 'wiki'
    template_name = "wiki_notification_email_template.txt"

    # IEmailDecorator methods

    def decorate_message(self, event, message, charset):
        if event.realm != self.realm:
            return
        # Set the subject
        subject = self._format_subject(event)
        set_header(message, 'Subject', subject, charset)
        # Attach diff, if configured that way.
        attach_diff = self.config.getbool('wiki-notification', 'attach_diff')
        if attach_diff:
            wikidiff = self._obtain_diff(event)
            part = MIMEText(wikidiff.encode('utf-8'), 'x-diff', charset)
            part['Content-Disposition'] = f'attachment; filename={event.target.name}.diff'
            message.attach(part)

    # INotificationFormatter methods

    def get_supported_styles(self, transport):
        yield 'text/plain', self.realm

    def format(self, transport, style, event):
        if event.realm != self.realm:
            return
        t = deactivate()
        try:
            return self._format_body(event)
        finally:
            reactivate(t)

    # Helper methods

    def _format_body(self, event):
        format_data = dict()
        format_data['action'] = event.category
        format_data['author'] = event.author
        format_data['name'] = event.target.name
        format_data['comment'] = event.comment
        format_data['text'] = event.target.text
        format_data['link'] = self.env.abs_href.wiki(event.target.name)
        format_data['linkdiff'] = self.env.abs_href.wiki(event.target.name, action='diff',
                                                         version=event.target.version)
        format_data['version'] = event.target.version
        attach_diff = self.config.getbool('wiki-notification', 'attach_diff')
        if attach_diff:
            format_data['wikidiff'] = None
        else:
            format_data['wikidiff'] = self._obtain_diff(event)
        chrome = Chrome(self.env)
        data = chrome.populate_data(None, format_data)
        template = chrome.load_template(self.template_name, text=True)
        body = chrome.render_template_string(template, data, text=True)
        return body.encode('utf-8')

    def _format_subject(self, event):
        template = self.config.get('wiki-notification', 'subject_template')
        prefix = self.config.get('notification', 'smtp_subject_prefix')
        if prefix == '__default__':
            prefix = f"[{self.config.get('project', 'name')}]"
        data = {'pagename': event.old_name or event.target.name,
                'prefix': prefix,
                'action': event.category,
                'env': self.env}
        return template.format(**data)

    def _obtain_diff(self, event):
        if event.category == 'modified' and event.target.version > 0:
            diff = diff_header.format(name=event.target.name,
                                      version=event.target.version,
                                      oldversion=event.target.version-1)
            oldpage = WikiPage(self.env, event.target.name, event.target.version - 1)
            for line in unified_diff(oldpage.text.splitlines(),
                                     event.target.text.splitlines(), context=3):
                diff += f"{line}\n"
        return diff
