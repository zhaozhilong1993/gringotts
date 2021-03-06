import functools
import time
import logging as log

from neutronclient.common import exceptions
from neutronclient.v2_0 import client as neutron_client
from oslo_config import cfg
import requests

from gringotts import constants as const
from gringotts.openstack.common import timeutils
from gringotts.services import keystone as ks_client
from gringotts.services import register
from gringotts.services import Resource
from gringotts.services import wrap_exception
from gringotts import utils


LOG = log.getLogger(__name__)
register = functools.partial(register,
                             ks_client,
                             service='network',
                             stopped_state=const.STATE_RUNNING)

OPTS = [
    cfg.BoolOpt('reserve_fip',
                default=True,
                help="Reserve floating ip or not when account owed")
]
cfg.CONF.register_opts(OPTS)


FIPSET_IS_AVAILABLE = None


def _floatingipset_available():
    global FIPSET_IS_AVAILABLE

    if FIPSET_IS_AVAILABLE is not None:
        return FIPSET_IS_AVAILABLE

    FIPSET_IS_AVAILABLE = True
    try:
        client = get_neutronclient(cfg.CONF.region_name)
        admin_tenant_id = ks_client.get_admin_tenant_id()
        client.list_floatingipsets(
            tenant_id=admin_tenant_id).get('floatingipsets')
    except Exception:
        LOG.warn("FloatingipSet is not avaliable")
        FIPSET_IS_AVAILABLE = False
    return FIPSET_IS_AVAILABLE


class FloatingIp(Resource):

    def to_message(self):
        msg = {
            'event_type': 'floatingip.create.end.again',
            'payload': {
                'floatingip': {
                    'id': self.id,
                    'uos:name': self.name,
                    'uos:service_provider': self.providers,
                    'rate_limit': self.size,
                    'tenant_id': self.project_id
                }
            },
            'timestamp': utils.format_datetime(timeutils.strtime())
        }
        return msg

    def to_env(self):
        """fack http env variables for use product items.
        :returns: env(dict)

        """
        return dict(HTTP_X_USER_ID=None, HTTP_X_PROJECT_ID=self.project_id)

    def to_body(self):
        """fack http body.
        :returns: body(dict)

        """
        body = {}
        body[self.resource_type] = dict(rate_limit=self.size)
        return body


class FloatingIpSet(Resource):
    def to_message(self):
        msg = {
            'event_type': 'floatingipset.create.end.again',
            'payload': {
                'floatingipset': {
                    'id': self.id,
                    'uos:name': self.name,
                    'uos:service_provider': self.providers,
                    'rate_limit': self.size,
                    'tenant_id': self.project_id
                }
            },
            'timestamp': utils.format_datetime(timeutils.strtime())
        }
        return msg


class Router(Resource):
    def to_message(self):
        msg = {
            'event_type': 'router.create.end.again',
            'payload': {
                'router': {
                    'id': self.id,
                    'name': self.name,
                    'tenant_id': self.project_id
                }
            },
            'timestamp': utils.format_datetime(timeutils.strtime())
        }
        return msg

    def to_env(self):
        return dict(HTTP_X_USER_ID=None, HTTP_X_PROJECT_ID=self.project_id)

    def to_body(self):
        return {}


class Listener(Resource):
    def to_message(self):
        msg = {
            'event_type': 'listener.create.end',
            'payload': {
                'listener': {
                    'id': self.id,
                    'name': self.name,
                    'admin_state_up': self.admin_state_up,
                    'connection_limit': self.connection_limit,
                    'tenant_id': self.project_id
                }
            },
            'timestamp': utils.format_datetime(timeutils.strtime())
        }
        return msg

    def to_env(self):
        return dict(HTTP_X_USER_ID=None, HTTP_X_PROJECT_ID=self.project_id)

    def to_body(self):
        body = {}
        body[self.resource_type] = dict(connection_limit=self.connection_limit)
        return body


class SecurityGroup(Resource):
    pass


class Loadbalancer(Resource):
    pass


class Network(Resource):
    pass


class Port(Resource):
    pass


def get_neutronclient(region_name=None):
    endpoint = ks_client.get_endpoint(region_name, 'network')
    auth_token = ks_client.get_token()
    c = neutron_client.Client(token=auth_token,
                              endpoint_url=endpoint)
    return c


@wrap_exception(exc_type='list')
def subnet_list(project_id, region_name=None):
    client = get_neutronclient(region_name)
    subnets = client.list_subnets(tenant_id=project_id).get('subnets')
    return subnets


@register(mtype='list')
@wrap_exception(exc_type='list')
def loadbalancer_list(project_id, region_name=None, project_name=None):
    client = get_neutronclient(region_name)
    lbs = client.list_loadbalancers(tenant_id=project_id).get('loadbalancers')
    formatted_loadbalancer = []
    for lb in lbs:
        formatted_loadbalancer.append(
            Loadbalancer(id=lb['id'],
                         name=lb['name'],
                         is_bill=False,
                         resource_type=const.RESOURCE_LOADBALANCER,
                         tenant_id=lb['tenant_id']))

    return formatted_loadbalancer

def loadbalancer_get(lb_id, region_name=None):
    return get_neutronclient(region_name).\
        show_loadbalancer(lb_id)['loadbalancer']

@register(mtype='list')
@wrap_exception(exc_type='list')
def security_group_list(project_id, region_name=None, project_name=None):
    client = get_neutronclient(region_name)
    sgs = client.list_security_groups(
        tenant_id=project_id).get('security_groups')
    formatted_security_group = []
    for sg in sgs:
        formatted_security_group.append(
            SecurityGroup(id=sg['id'],
                          name=sg['name'],
                          is_bill=False,
                          resource_type=const.RESOURCE_SECURITY_GROUP,
                          tenant_id=sg['tenant_id']))
    return formatted_security_group


@wrap_exception(exc_type='list')
def pool_list(project_id, region_name=None):
    client = get_neutronclient(region_name)
    pools = client.list_lbaas_pools(tenant_id=project_id).get('pools')
    return pools


@register(mtype='list')
@wrap_exception(exc_type='list')
def port_list(project_id, region_name=None, device_id=None, project_name=None):
    client = get_neutronclient(region_name)
    if device_id:
        ports = client.list_ports(tenant_id=project_id,
                                  device_id=device_id).get('ports')
    else:
        ports = client.list_ports(tenant_id=project_id).get('ports')

    formatted_ports = []
    for port in ports:
        status = utils.transform_status(port['status'])
        formatted_ports.append(Port(id=port['id'],
                                    name=port['name'],
                                    is_bill=False,
                                    resource_type='port',
                                    status=status,
                                    project_id=port['tenant_id'],
                                    project_name=project_name,
                                    original_status=port['status']))

    return formatted_ports


@register(mtype='list')
@wrap_exception(exc_type='list')
def network_list(project_id, region_name=None, project_name=None):
    client = get_neutronclient(region_name)
    networks = client.list_networks(tenant_id=project_id).get('networks')
    formatted_networks = []
    for network in networks:
        status = utils.transform_status(network['status'])
        formatted_networks.append(Network(id=network['id'],
                                          name=network['name'],
                                          is_bill=False,
                                          resource_type='network',
                                          status=status,
                                          project_id=network['tenant_id'],
                                          project_name=project_name,
                                          original_status=network['status']))
    return formatted_networks


@register(resource=const.RESOURCE_FLOATINGIP, mtype='get')
@wrap_exception(exc_type='get')
def floatingip_get(fip_id, region_name=None):
    try:
        fip = get_neutronclient(
            region_name).show_floatingip(fip_id).get('floatingip')
    except exceptions.NotFound:
        return None
    except exceptions.NeutronException as e:
        if e.status_code == 404:
            return None
        raise e
    status = utils.transform_status(fip['status'])
    return FloatingIp(id=fip['id'],
                      name=fip['uos:name'],
                      providers=fip['uos:service_provider'],
                      resource_type=const.RESOURCE_FLOATINGIP,
                      status=status,
                      original_status=fip['status'],
                      is_reserved=True)


@register(resource=const.RESOURCE_FLOATINGIPSET, mtype='get')
@wrap_exception(exc_type='get')
def floatingipset_get(fipset_id, region_name=None):
    try:
        client = get_neutronclient(region_name)
        fipset = client.show_floatingipset(fipset_id).get('floatingipset')
    except (exceptions.NotFound):
        return None
    except (exceptions.NeutronException) as e:
        if e.status_code == 404:
            return None
        raise e

    status = utils.transform_status(fipset['status'])
    return FloatingIpSet(id=fipset['id'],
                         name=fipset['uos:name'],
                         providers=fipset['uos:service_provider'],
                         resource_type=const.RESOURCE_FLOATINGIPSET,
                         status=status,
                         original_status=fipset['status'],
                         is_reserved=True)


@register(resource=const.RESOURCE_ROUTER, mtype='get')
@wrap_exception(exc_type='get')
def router_get(router_id, region_name=None):
    try:
        router = get_neutronclient(
            region_name).show_router(router_id).get('router')
    except exceptions.NotFound:
        return None
    except exceptions.NeutronException as e:
        if e.status_code == 404:
            return None
        raise e
    status = utils.transform_status(router['status'])
    return Router(id=router['id'],
                  name=router['name'],
                  resource_type=const.RESOURCE_ROUTER,
                  status=status,
                  original_status=router['status'])


@register(mtype='list')
@wrap_exception(exc_type='list')
def floatingip_list(project_id, region_name=None, project_name=None):
    client = get_neutronclient(region_name)
    if project_id:
        fips = client.list_floatingips(tenant_id=project_id).get('floatingips')
    else:
        fips = client.list_floatingips().get('floatingips')
    formatted_fips = []
    for fip in fips:
        created_at = utils.format_datetime(fip['created_at'])
        status = utils.transform_status(fip['status'])
        is_bill = False if fip.get('floatingipset_id') else True
        formatted_fips.append(
            FloatingIp(id=fip['id'],
                       name=fip['uos:name'],
                       is_bill=is_bill,
                       size=fip['rate_limit'],
                       providers=fip['uos:service_provider'],
                       project_id=fip['tenant_id'],
                       project_name=project_name,
                       resource_type=const.RESOURCE_FLOATINGIP,
                       status=status,
                       original_status=fip['status'],
                       created_at=created_at))

    return formatted_fips


@register(mtype='list',
          function_available=_floatingipset_available)
@wrap_exception(exc_type='list')
def floatingipset_list(project_id, region_name=None, project_name=None):
    client = get_neutronclient(region_name)
    if project_id:
        _fipsets = client.list_floatingipsets(
            tenant_id=project_id).get('floatingipsets')
        fipsets = [fip for fip in _fipsets if fip['tenant_id'] == project_id]

    else:
        fipsets = client.list_floatingipsets().get('floatingipsets')

    formatted_fipsets = []
    for fipset in fipsets:
        created_at = utils.format_datetime(fipset['created_at'])
        status = utils.transform_status(fipset['status'])
        formatted_fipsets.append(
            FloatingIpSet(id=fipset['id'],
                          name=fipset['uos:name'],
                          size=fipset['rate_limit'],
                          providers=fipset['uos:service_provider'],
                          project_id=fipset['tenant_id'],
                          project_name=project_name,
                          resource_type=const.RESOURCE_FLOATINGIPSET,
                          status=status,
                          original_status=fipset['status'],
                          created_at=created_at))

    return formatted_fipsets


@wrap_exception(exc_type='list')
def port_forwarding_list(project_id, region_name=None, project_name=None):
    client = get_neutronclient(region_name)
    routers = router_list(project_id, region_name, project_name)
    portforwardings = []
    for router in routers:
        router_id = router['id']
        router_detail = client.show_router(router_id)
        port_forwarding = router_detail['router']['portforwardings']
        if port_forwarding:
            portforwardings.append(port_forwarding)
    return portforwardings


@register(mtype='list')
@wrap_exception(exc_type='list')
def router_list(project_id, region_name=None, project_name=None):
    client = get_neutronclient(region_name)
    if project_id:
        routers = client.list_routers(tenant_id=project_id).get('routers')
    else:
        routers = client.list_routers().get('routers')
    formatted_routers = []
    for router in routers:
        created_at = utils.format_datetime(router['created_at'])
        status = utils.transform_status(router['status'])
        formatted_routers.append(Router(id=router['id'],
                                        name=router['name'],
                                        project_id=router['tenant_id'],
                                        project_name=project_name,
                                        resource_type=const.RESOURCE_ROUTER,
                                        status=status,
                                        original_status=router['status'],
                                        created_at=created_at))
    return formatted_routers


@register(mtype='deletes')
@wrap_exception(exc_type='bulk')
def delete_fips(project_id, region_name=None):
    client = get_neutronclient(region_name)

    # Get floating ips
    fips = client.list_floatingips(tenant_id=project_id)
    fips = fips.get('floatingips')

    # Disassociate these floating ips
    update_dict = {'port_id': None}
    for fip in fips:
        try:
            client.update_floatingip(fip['id'],
                                     {'floatingip': update_dict})
        except Exception:
            pass

    # Release these floating ips
    for fip in fips:
        try:
            client.delete_floatingip(fip['id'])
            LOG.warn("Delete floatingip: %s" % fip['id'])
        except Exception:
            pass


@register(mtype='deletes',
          function_available=_floatingipset_available)
@wrap_exception(exc_type='bulk')
def delete_fipsets(project_id, region_name=None):
    client = get_neutronclient(region_name)

    fipsets = client.list_floatingipsets(tenant_id=project_id)
    fipsets = fipsets.get('floatingipsets')

    update_dict = {'port_id': None}
    for fipset in fipsets:
        try:
            client.update_floatingipset(
                fipset['id'], {'floatingipset': update_dict})
        except (Exception):
            pass

    for fipset in fipsets:
        try:
            client.delete_floatingipset(fipset['id'])
            LOG.warn('Delete floatingipset: %s', fipset['id'])
        except (Exception):
            pass


@register(mtype='deletes')
@wrap_exception(exc_type='bulk')
def delete_networks(project_id, region_name=None):
    client = get_neutronclient(region_name)

    from gringotts.services import nova
    nova_client = nova.get_novaclient(region_name)

    # delete all ports
    ports = client.list_ports(tenant_id=project_id).get('ports')
    for port in ports:
        try:
            if port['device_owner'] == 'network:router_interface':
                body = dict(subnet_id=port['fixed_ips'][0]['subnet_id'])
                client.remove_interface_router(port['device_id'], body)
            elif port['device_owner'] == 'compute:None':
                nova_client.servers.interface_detach(
                    port['device_id'], port['id'])
                time.sleep(1)  # wait a second to detach interface
                try:
                    client.delete_port(port['id'])
                except Exception:
                    time.sleep(1)
                    client.delete_port(port['id'])
            elif port['device_owner'] == '':
                client.delete_port(port['id'])
        except Exception:
            pass

    # delete all subnets
    subnets = client.list_subnets(tenant_id=project_id).get('subnets')
    for subnet in subnets:
        try:
            client.delete_subnet(subnet['id'])
        except Exception:
            pass

    # delete all networks
    networks = client.list_networks(tenant_id=project_id).get('networks')
    for network in networks:
        try:
            client.delete_network(network['id'])
        except Exception:
            pass


@register(mtype='deletes')
@wrap_exception(exc_type='bulk')
def delete_security_groups(project_id, region_name=None):
    client = get_neutronclient(region_name)
    security_groups = client.list_security_groups(
        tenant_id=project_id).get('security_groups')

    for security_group in security_groups:
        ports = client.list_ports(tenant_id=project_id).get('ports')
        for port in ports:
            if security_group['id'] in port['security_groups']:
                client.delete_port(port['id'])
        client.delete_security_group(security_group['id'])
        LOG.warn("Delete security_group: %s" % security_group['id'])


@register(mtype='deletes')
@wrap_exception(exc_type='bulk')
def delete_loadbalancers(project_id, region_name=None):
    client = get_neutronclient(region_name)
    loadbalancers = client.list_loadbalancers(
        tenant_id=project_id).get('loadbalancers')

    # delete the listeners first
    delete_listeners(project_id, region_name)

    for loadbalancer in loadbalancers:
        client.delete_loadbalancer(loadbalancer['id'])
        LOG.warn("Delete loadbalancer: %s" % loadbalancer['id'])


@register(mtype='deletes')
@wrap_exception(exc_type='bulk')
def delete_routers(project_id, region_name=None):
    client = get_neutronclient(region_name)

    routers = client.list_routers(tenant_id=project_id).get('routers')
    for router in routers:
        try:
            # Delete VPNs of this router
            vpns = client.list_pptpconnections(
                router_id=router['id']).get('pptpconnections')
            for vpn in vpns:
                client.delete_pptpconnection(vpn['id'])

            # Delete tunnel of this router
            tunnels = router.get('tunnels')
            if tunnels:
                _delete_tunnels(tunnels, region_name=region_name)

            # Remove floatingips of this router
            fips = client.list_floatingips(
                tenant_id=project_id).get('floatingips')
            update_dict = {'port_id': None}
            for fip in fips:
                client.update_floatingip(fip['id'],
                                         {'floatingip': update_dict})

            # Remove gateway
            client.remove_gateway_router(router['id'])

            # Get interfaces of this router
            ports = client.list_ports(tenant_id=project_id,
                                      device_id=router['id']).get('ports')

            # Clear these interfaces from this router
            body = {}
            for port in ports:
                body['port_id'] = port['id']
                client.remove_interface_router(router['id'], body)

            # And then delete this router
            client.delete_router(router['id'])
            LOG.warn("Delete router: %s" % router['id'])
        except Exception:
            LOG.error("Fail to delete router: %s" % router['id'])


@register(resource=const.RESOURCE_FLOATINGIP, mtype='delete')
@wrap_exception(exc_type='delete')
def delete_fip(fip_id, region_name=None):
    client = get_neutronclient(region_name)
    update_dict = {'port_id': None}
    client.update_floatingip(fip_id,
                             {'floatingip': update_dict})
    client.delete_floatingip(fip_id)


@register(resource=const.RESOURCE_FLOATINGIPSET, mtype='delete')
@wrap_exception(exc_type='delete')
def delete_fipset(fipset_id, region_name):
    client = get_neutronclient(region_name)
    update_dict = {'port_id': None}
    client.update_floatingipset(
        fipset_id, {'floatingipset': update_dict})
    client.delete_floatingip(fipset_id)


@register(resource=const.RESOURCE_FLOATINGIP, mtype='stop')
@wrap_exception(exc_type='stop')
def stop_fip(fip_id, region_name=None):
    client = get_neutronclient(region_name)

    try:
        fip = client.show_floatingip(fip_id).get('floatingip')
    except exceptions.NotFound:
        return False
    except exceptions.NeutronException as e:
        if e.status_code == 404:
            return False

    if cfg.CONF.reserve_fip:
        return True

    if fip and fip['uos:registerno']:
        return True

    update_dict = {'port_id': None}
    client.update_floatingip(fip_id,
                             {'floatingip': update_dict})
    client.delete_floatingip(fip_id)
    return False


@register(resource=const.RESOURCE_FLOATINGIPSET, mtype='stop')
@wrap_exception(exc_type='stop')
def stop_fipset(fipset_id, region_name=None):
    client = get_neutronclient(region_name)

    try:
        fipset = client.show_floatingipset(fipset_id)
        fipset = fipset.get('floatingipset')
    except (exceptions.NotFound):
        return False
    except (exceptions.NeutronException) as e:
        if e.stataus_code == 404:
            return False

    if cfg.CONF.reserve_fip:
        return True

    update_dict = {'port_id': None}
    client.update_floatingipset(
        fipset_id, {'floatingipset': update_dict})
    client.delete_floatingipset(fipset_id)

    return False


@wrap_exception(exc_type='bulk')
def _delete_tunnels(tunnels, region_name=None):
    endpoint = ks_client.get_endpoint(region_name, 'network')
    auth_token = ks_client.get_token()
    path = "%s/v2.0/uos_resources/%s/remove_tunnel.json" % (
        endpoint.rstrip('/'), '%s')
    for tunnel in tunnels:
        url = path % tunnel
        try:
            requests.put(url, headers={'X-Auth-Token': auth_token})
        except Exception as e:
            LOG.error('Fail to delete tunnel: %s, as: %s' % (tunnel, e))


@register(resource=const.RESOURCE_ROUTER, mtype='delete')
@wrap_exception(exc_type='delete')
def delete_router(router_id, region_name=None):
    client = get_neutronclient(region_name)

    router = client.show_router(router_id).get('router')

    # Delete VPNs of this router
    vpns = client.list_pptpconnections(
        router_id=router_id).get('pptpconnections')
    for vpn in vpns:
        client.delete_pptpconnection(vpn['id'])

    # Delete tunnel of this router
    tunnels = router.get('tunnels')
    if tunnels:
        _delete_tunnels(tunnels, region_name=region_name)

    # Remove floatingips of this router
    project_id = router['tenant_id']
    fips = client.list_floatingips(tenant_id=project_id).get('floatingips')
    update_dict = {'port_id': None}
    for fip in fips:
        client.update_floatingip(fip['id'],
                                 {'floatingip': update_dict})

    # Remove subnets of this router
    ports = client.list_ports(device_id=router_id).get('ports')
    for port in ports:
        body = {}
        if port['device_owner'] == 'network:router_interface':
            body['subnet_id'] = port['fixed_ips'][0]['subnet_id']
            client.remove_interface_router(router_id, body)

    time.sleep(5)
    # And then delete this router
    client.delete_router(router_id)


@register(resource=const.RESOURCE_ROUTER, mtype='stop')
@wrap_exception(exc_type='stop')
def stop_router(router_id, region_name=None):
    return True


@register(mtype='list')
@wrap_exception(exc_type='list')
def listener_list(project_id, region_name=None, project_name=None):
    client = get_neutronclient(region_name)
    if project_id:
        listeners = client.list_listeners(
            tenant_id=project_id).get('listeners')
    else:
        listeners = client.list_listeners().get('listeners')

    formatted_listeners = []
    for listener in listeners:
        status = utils.transform_status(listener['status'])
        admin_state = (const.STATE_RUNNING
                       if listener['admin_state_up']
                       else const.STATE_STOPPED)
        created_at = utils.format_datetime(
            listener.get('created_at', timeutils.strtime()))
        formatted_listeners.append(
            Listener(id=listener['id'],
                     name=listener['name'],
                     admin_state_up=listener['admin_state_up'],
                     admin_state=admin_state,
                     connection_limit=listener['connection_limit'],
                     project_id=listener['tenant_id'],
                     project_name=project_name,
                     resource_type=const.RESOURCE_LISTENER,
                     status=status,
                     original_status=listener['status'],
                     created_at=created_at))

    return formatted_listeners


@register(mtype='deletes')
@wrap_exception(exc_type='bulk')
def delete_listeners(project_id, region_name=None):
    client = get_neutronclient(region_name)
    listeners = client.list_listeners(tenant_id=project_id).get('listeners')
    for listener in listeners:
        try:
            client.delete_listener(listener['id'])
            LOG.warn("Delete listener: %s" % listener['id'])
        except Exception:
            LOG.error("Fail to delete listener: %s" % listener['id'])


def _is_last_up_listener(client, loadbalancer_id, listener_id):
    lb = client.show_loadbalancer(loadbalancer_id).get('loadbalancer')
    up_listeners = []
    for lid in lb['listener_ids']:
        listener = client.show_listener(lid).get('listener')
        if listener['admin_state_up']:
            up_listeners.append(lid)
    if len(up_listeners) == 1 and listener_id in up_listeners:
        return True
    return False


@register(resource=const.RESOURCE_LISTENER,
          mtype='get', stopped_state=const.STATE_STOPPED)
@wrap_exception(exc_type='get')
def listener_get(listener_id, region_name=None):
    client = get_neutronclient(region_name)
    try:
        listener = client.show_listener(listener_id).get('listener')
    except exceptions.NotFound:
        return None
    except exceptions.NeutronException as e:
        if e.status_code == 404:
            return None
        raise e

    is_last_up = _is_last_up_listener(
        client, listener['loadbalancer_id'], listener_id)
    status = utils.transform_status(listener['status'])
    admin_state = (const.STATE_RUNNING
                   if listener['admin_state_up']
                   else const.STATE_STOPPED)

    return Listener(id=listener['id'],
                    name=listener['name'],
                    resource_type=const.RESOURCE_LISTENER,
                    status=status,
                    admin_state=admin_state,
                    is_last_up=is_last_up,
                    original_status=listener['status'])


@register(resource=const.RESOURCE_LISTENER, mtype='stop')
@wrap_exception(exc_type='stop')
def stop_listener(listener_id, region_name=None):
    client = get_neutronclient(region_name)
    update_dict = {'admin_state_up': False}
    client.update_listener(listener_id, {'listener': update_dict})


@register(resource=const.RESOURCE_LISTENER, mtype='delete')
@wrap_exception(exc_type='delete')
def delete_listener(listener_id, region_name=None):
    client = get_neutronclient(region_name)
    client.delete_listener(listener_id)
    LOG.warn("Delete listener: %s" % listener_id)


@wrap_exception(exc_type='put')
def quota_update(project_id, user_id=None, region_name=None, **kwargs):
    """Update quota of networks service.
    kwargs = {"floatingip": 10,
              "network": 20,
              "router": 1024,
              ...}
    """
    client = get_neutronclient(region_name)
    body = {
        "quota": kwargs
    }
    client.update_quota(project_id, body=body)


@wrap_exception(exc_type='get')
def quota_get(project_id, region_name=None):
    """Get quota of networks service.
    {u'quota': {u'floatingip': 20,
                u'listener': 6,
                u'loadbalancer': 3,
                u'network': 10,
                u'pool': 6,
                u'router': 11,
                u'subnet': 10}}
    """
    client = get_neutronclient(region_name)
    limit = client.show_quota(project_id).get('quota')

    fip_n = len(floatingip_list(project_id, region_name))
    listener_n = len(listener_list(project_id, region_name))
    lb_n = len(loadbalancer_list(project_id, region_name))
    net_n = len(network_list(project_id, region_name))
    subnet_n = len(subnet_list(project_id, region_name))
    pool_n = len(pool_list(project_id, region_name))
    router_n = len(router_list(project_id, region_name))
    sg_n = len(security_group_list(project_id, region_name))
    pf_n = len(port_forwarding_list(project_id, region_name))

    quota = {
        'floatingip': {'in_use': fip_n, 'limit': limit.get('floatingip')},
        'listener': {'in_use': listener_n, 'limit': limit.get('listener')},
        'loadbalancer': {'in_use': lb_n, 'limit': limit.get('loadbalancer')},
        'network': {'in_use': net_n, 'limit': limit.get('network')},
        'pool': {'in_use': pool_n, 'limit': limit.get('pool')},
        'router': {'in_use': router_n, 'limit': limit.get('router')},
        'security_group': {
            'in_use': sg_n, 'limit': limit.get('security_group')
        },
        'subnet': {'in_use': subnet_n, 'limit': limit.get('subnet')},
        'portforwardings': {
            'in_use': pf_n, 'limit': limit.get('portforwardings')
        }
    }

    return quota
