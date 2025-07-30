jQuery(document).ready(function($) {
    $("#ctxtnav ul li.last").removeAttr("class").after($("<li>").addClass("last").html($("<a>").attr("href", wiki_notification.href).attr("title", wiki_notification.title).text(wiki_notification.title)));
});
