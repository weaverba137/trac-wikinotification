=============================
Trac Wiki Notification Plugin
=============================

Introduction
------------

Trac WikiNotification is a plugin that allows users (even anonymous,
as long as an email is set) to select the wiki pages that they wish to
be notified (by email) when a change occurs to it.

Enabling the Plugin
-------------------

It's as simple as:

.. sourcecode:: ini

    [components]
    wikinotification.* = enabled

``smtp_enabled`` has to be enabled in ``notification`` configuration section.

Available Configuration Options
-------------------------------

These are the options available to include on your ``trac.ini`` under
``[wiki-notification]``. You can also configure them through the web admin interface.

===================== ================================ ========================
Config Setting        Default Value                    Explanation
===================== ================================ ========================
*from_email*          trac.wiki\@localhost             Sender address to use in
                                                       notification emails.
--------------------- -------------------------------- ------------------------
*from_name*           None                             Sender name to use in
                                                       notification emails.
                                                       Defaults to project name.
--------------------- -------------------------------- ------------------------
*smtp_always_cc*      *empty*                          Comma separated list of
                                                       email address(es) to
                                                       always send notifications
                                                       to, addresses can be seen
                                                       by all recipients (Cc:).
--------------------- -------------------------------- ------------------------
*smtp_always_bcc*     *empty*                          Comma separated list of
                                                       email address(es) to
                                                       always send notifications
                                                       to, addresses do not
                                                       appear publicly (Bcc:).
--------------------- -------------------------------- ------------------------
*use_public_cc*       False                            Recipients can see email
                                                       addresses of other CCed
                                                       recipients. If this option
                                                       is disabled (the default),
                                                       recipients are put on BCC.
--------------------- -------------------------------- ------------------------
*attach_diff*         False                            Send changes diff as an
                                                       attachment instead of on
                                                       the email text body.
--------------------- -------------------------------- ------------------------
*notify_author*       False                            Normally authors are not
                                                       notified if they themselves
                                                       make a change to a page
                                                       they are watching. Enable
                                                       this setting to notify
                                                       authors of their own changes.
--------------------- -------------------------------- ------------------------
*redirect_time*       5 (in seconds)                   The default seconds a
                                                       redirect should take when
                                                       watching/un-watching a
                                                       wiki page.
                                                       This value is also
                                                       definable per user.
--------------------- -------------------------------- ------------------------
*subject_template*    ``{prefix} {pagename} {action}`` A Python
                                                       ``str.format()``-style
                                                       text template snippet
                                                       used to create the
                                                       notification subject.
--------------------- -------------------------------- ------------------------
*banned_addresses*    *empty*                          Comma-separated list of
                                                       email addresses to never
                                                       send notifications to.
===================== ================================ ========================

Here is an example of the settings:

.. sourcecode:: ini

    [wiki-notification]
    redirect_time = 5
    smtp_always_bcc = someone@somedomain, another.one@somedomain
    smtp_always_cc = someone.else@somedomain
    from_email = trac.wiki@localhost
    from_name = Custom Name
    use_public_cc = false
    attach_diff = true
    subject_template = Foo {prefix} {pagename} {action}
    banned_addresses = banned.user1@somedomain, banned.user2@somedomain

Download and Installation
-------------------------

Run the following to install this plugin:

.. sourcecode:: sh

   > sudo pip install TracWikiNotification

Aditional Notes (from user input)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* ``pip`` is run from the command line (on Linux) not from within Python.
* After installing any plugin for Trac you'll need to restart Apache to see
  it (not all changes to trac.ini require a restart but adding a plugin does).
* Setting the ``notify_author`` option (see above) to ``True`` is a great way
  to test the plugin.

Tweaking/Customizing The Notification Email Template
----------------------------------------------------

You can, if you wish, tweak the notification email template sent to your users.

Copy the ``wiki_notification_email_template.txt`` file to your trac environment
``templates/`` sub-directory and tweak it to your needs.

Make sure you read the `Jinja2 Text Templates`_ documentation to see if you don't
break any of the logic in that template.

.. _`Jinja2 Text Templates`: https://trac.edgewall.org/wiki/TracDev/HtmlTemplates#Jinja2architecture
