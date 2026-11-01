"""Options registered before Zun parses its configuration."""
from oslo_config import cfg

GROUP = 'afterglow_cloud_shell'
BASE_CIDRS = ('169.254.169.254/32', 'fd00:ec2::254/128', 'fe80::a9fe:a9fe/128')
OPTS = [
    cfg.BoolOpt('enabled', default=False),
    cfg.StrOpt('service_project_id', default=''),
    cfg.StrOpt('service_user_id', default=''),
    cfg.ListOpt('blocked_cidrs', default=list(BASE_CIDRS)),
    cfg.StrOpt('lock_path', default='/var/lib/zun/cloud-shell-locks',
               help='Private host-local directory shared by native Zun workers.'),
    cfg.StrOpt('sandbox_image', default='', help=(
        'Digest-pinned native holder image built from sandbox/Dockerfile; '
        'its only executable is /pause. Qualify before enabling.')),
]

def register_opts(conf):
    conf.register_opts(OPTS, group=GROUP)
