"""
Helper methods to generate dynamic Bootstrap-specific content,
and correctly call htmlfill with the right formatting in
a Bootstrap-aware context.
"""
from formencode import htmlfill

def tw_bootstrap_error_formatter(error):
    return '<span class="help-error">%s</span>' % htmlfill.html_quote(error)

def tw_bootstrap_alert_error_formatter(error):
    return """
    <div class="alert-message block-message error">
        <p>%s</p>
    </div>
    """ % htmlfill.html_quote(error)

def tw_bootstrap_warning_error_formatter(error):
    return """
    <div class="alert-message block-message warning">
        <p>%s</p>
    </div>
    """ % htmlfill.html_quote(error)

# shitty shitty defaults
tw_bootstrap_error_formatters = {
    'default': tw_bootstrap_error_formatter
}

tw_bootstrap_alert_error_formatters = {
    'default': tw_bootstrap_error_formatter,
    'block': tw_bootstrap_alert_error_formatter
}

tw_bootstrap_warning_error_formatters = {
    'default': tw_bootstrap_error_formatter,
    'block': tw_bootstrap_warning_error_formatter
}


# TODO: seems to be only needed as part of session context?
# investigate why this needed for sequence flow and not for batch plates
def render_bootstrap_form(response, **htmlfill_kwargs):
    htmlfill_kwargs2 = dict(htmlfill_kwargs)
    if htmlfill_kwargs.get('auto_error_formatter', None) is None:
        htmlfill_kwargs2['auto_error_formatter'] = tw_bootstrap_error_formatter
    else:
        htmlfill_kwargs2 = htmlfill_kwargs

    return htmlfill.render(response, **htmlfill_kwargs2)