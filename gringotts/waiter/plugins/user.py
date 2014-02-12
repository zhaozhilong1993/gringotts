#!/usr/bin/python
"""Handle user registeration
"""
from decimal import Decimal
from oslo.config import cfg

from gringotts import context
from gringotts import db
from gringotts.db import models as db_models
from gringotts import exception
from gringotts import plugin

from gringotts.openstack.common import log


LOG = log.getLogger(__name__)


OPTS = [
    cfg.StrOpt('keystone_control_exchange',
               default='keystone',
               help="Exchange name for Keystone notifications"),
]


cfg.CONF.register_opts(OPTS)

db_conn = db.get_connection(cfg.CONF)


class RegisterNotificationBase(plugin.NotificationBase):
    @staticmethod
    def get_exchange_topics(conf):
        """Return a sequence of ExchangeTopics defining the exchange and
        topics to be connected for this plugin.
        """
        return [
            plugin.ExchangeTopics(
                exchange=conf.keystone_control_exchange,
                topics=set(topic + ".info"
                           for topic in conf.notification_topics)),
        ]


class UserRegisterEnd(RegisterNotificationBase):
    """Handle the event that volume be created
    """
    event_types = ['identity.account.register']

    def process_notification(self, message):
        LOG.debug('Do action for event: %s', message['event_type'])

        try:
            user_id = message['payload']['user_id']
            project_id = message['payload']['project_id']
            account = db_models.Account(user_id, project_id,
                                        Decimal(cfg.CONF.waiter.initial_balance),
                                        Decimal('0'), 'CNY')
            db_conn.create_account(context.get_admin_context(), account)
        except Exception:
            LOG.exception('Fail to create account for the project: %s' %
                          project_id)
            raise exception.AccountCreateFailed(project_id=project_id)
        LOG.debug('Create account for the project %s successfully' % project_id)
