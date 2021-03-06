Installation
============

1. Get source code::

    $ git clone git@git.ustack.com:ustack/gringotts.git
    $ cd gringotts

2. Create virtualenv environment::

    $ virtualenv .venv
    $ source .venv/bin/activate

3. Install dependents::

    $ pip install -r requirements.txt
    $ pip install -r test-requirements.txt

4. Install gringotts::

    $ python setup.py develop

5. Copy etc/gringotts/* to /etc/gringotts/::

    $ cp etc/gringotts/gringotts.conf.sample /etc/gringotts/gringotts.conf
    $ cp etc/gringotts/gringotts.json /etc/gringotts/gringotts.json

6. Change config options as your needed::

    [DEFAULT]
    rabbit_host=localhost
    rabbit_port=5672
    rabbit_userid=guest
    rabbit_password=rachel

    auth_strategy=keystone
    debug=True

    [waiter]
    queue_name=gringotts.notification
    initial_balance=10

    [master]
    use_local=Flase
    reserved_days=7

    [worker]
    protocol=local

    [database]
    connection=mysql://root:admin@localhost/gringotts?charset=utf8

    [keystone_authtoken]
    auth_protocol=http
    auth_host=127.0.0.1
    auth_port=35357
    auth_version=v3.0
    admin_user=admin
    admin_password=admin
    admin_tenant_name=admin

7. Initialize database::

   $ gring-dbsync

8. Start gringotts::

    $ gring-api
    $ gring-waiter
    $ gring-master
