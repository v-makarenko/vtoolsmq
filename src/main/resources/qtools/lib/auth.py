"""
Methods to help with authentication tasks, particularly with LDAP and
Active Directory.
"""

from wowo import wowo
from pylons.controllers.util import abort
from pylons import response
from paste.request import parse_dict_querystring
from repoze.who.plugins.form import RedirectingFormPlugin
from repoze.who.plugins.ldap import LDAPSearchAuthenticatorPlugin, LDAPAttributesPlugin
from repoze.what.plugins.ini import INIGroupAdapter
from repoze.what.plugins.pylonshq import ActionProtector
from base64 import b64decode
import ldap, time

class BioRadAuthenticatorPlugin(LDAPSearchAuthenticatorPlugin):
    """
    Because our Active Directory suuuuckkks
    """
    def __init__(self, *args, **kwargs):
        ldap.set_option(ldap.OPT_REFERRALS, 0)
        super(BioRadAuthenticatorPlugin, self).__init__(*args, **kwargs)
        self.bind_password = self.bind_pass

    def _get_dn(self, environ, identity):
        """
        Exactly like repoze.who.plugins.ldap.LDAPSearchAuthenticatorPlugin._get_dn,
        except returns the first response if the server returns more than two entries
        when matching against the DN lookup.

        Otherwise, piggybacks on LDAPSearchAuthenticatorPlugin as a hack.
        """

        if self.bind_dn:
            try:
                self.ldap_connection.bind_s(self.bind_dn, self.bind_password)
            except ldap.LDAPError:
                raise ValueError("Couldn't bind with supplied credentials")
        try:
            login_name = identity['login'].replace('*',r'\*')
            srch = self.search_pattern % login_name
            dn_list = self.ldap_connection.search_s(
                self.base_dn,
                self.search_scope,
                srch,
                )

            # here is the change; return the CN of the first.
            if len(dn_list) >= 1:
                return dn_list[0][0]
            else:
                raise ValueError('No entry found for %s' %srch)
        except (KeyError, TypeError, ldap.LDAPError):
            raise # ValueError

class BioRadSimpleLoginAdapter(LDAPAttributesPlugin):
    """
    Grabs additional attributes to store in repoze.who, and
    then converts the user credentials back to the login name.
    This is required because the full LDAP user credential is
    super long, and we want to use the sAMAccountName in
    the group.ini and permissions.ini file.
    """
    # next step is to cache this stuff in beaker on lookup... but for now it's OK.
    def add_metadata(self, environ, identity):
        super(BioRadSimpleLoginAdapter, self).add_metadata(environ, identity)
        for a in self.attributes:
            # this happens because the attributes are all lists-- return the first entry
            identity['repoze.who.%s' % a] = identity[a][0]

class BioRadCachedLoginAdapter(BioRadSimpleLoginAdapter):
    """
    Stores LDAP attribute metadata in a Beaker session.
    """
    def __init__(self, ldap_connection, *args, **kwargs):
        self.key_name = kwargs.pop('key_name', 'repoze.what.ldap.tkt')
        self.session_name = kwargs.pop('session_name', 'beaker.session')
        self.max_age = kwargs.pop('max_age', 24*60*60)
        super(BioRadCachedLoginAdapter, self).__init__(ldap_connection, *args, **kwargs)

    def _get_beaker(self, environ):
        s = environ.get(self.session_name, None)
        if not s:
            raise ValueError, ("No Beaker session (%s) in environment" % self.session_name)
        return s

    def add_metadata(self, environ, identity):
        dnmatch = self.dnrx.match(identity.get('userdata', ''))
        if dnmatch:
            dn = b64decode(dnmatch.group('b64dn'))
        else:
            dn = identity.get('repoze.who.userid')

        s = self._get_beaker(environ)
        last_userid = s.get("%s.userid" % self.key_name)
        expires = s.get("%s.expires" % self.key_name)

        use_cached = False
        if last_userid == dn:
            if expires:
                if int(time.time()) <= expires:
                    for key, val in s.items():
                        if key.startswith(self.key_name) and not key.endswith(('expires','userid')):
                            identity['repoze.who.%s' % key[(len(self.key_name)+1):]] = val
                    return

        # otherwise, just do super and cache
        super(BioRadCachedLoginAdapter, self).add_metadata(environ, identity)
        s['%s.expires' % self.key_name] = int(time.time()) + self.max_age
        s['%s.userid' % self.key_name] = dn
        for a in self.attributes:
            if a not in ('expires',):
                s['%s.%s' % (self.key_name, a)] = identity['repoze.who.%s' % a]
        s.save()


class BioRadRoleAdapter(INIGroupAdapter):
    """
    Overrides default to tie group to the sAMAccountName, rather than the userid.
    """
    def __init__(self, filename, identity_param):
        self.identity_param = identity_param
        super(INIGroupAdapter, self).__init__(filename)

    def _find_sections(self, hint):
        """
        Lifted from original, just changes hint source
        """
        userid = hint[self.identity_param]
        answer = set()
        for section in self.info.keys():
            if userid in self.info[section]:
                answer.add(section)
        return answer

class WowoActionProtector(ActionProtector):
    """
    Only protect an action if authorization is on in the app config.
    """
    def wrap_action(self, action_, *args, **kwargs):
        if not wowo('auth'):
            return action_(*args, **kwargs)
        else:
            return super(WowoActionProtector, self).wrap_action(action_, *args, **kwargs)

class RestrictedWowoActionProtector(ActionProtector):
    """
    Only allow an action to pass through if authorization is enabled
    in the app config, and if the user has permission.

    Will behave the same as WowoActionProtector if authorization is
    enabled, but if authorization is not specified in auth.ini,
    will raise a 403.
    """
    def wrap_action(self, action_, *args, **kwargs):
        if not wowo('auth'):
            reason = "Access to restricted areas has been disabled."
            if self.denial_handler:
                response.status = 403
                return self.denial_handler(reason)
            else:
                abort(403, comment=reason)
        else:
            return super(RestrictedWowoActionProtector, self).wrap_action(action_, *args, **kwargs)