import importlib.util
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('observer',Path(__file__).resolve().parents[1]/'server.py')
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
H=m.HOSTS['dev-backend']

class ObserverTests(unittest.TestCase):
    def setUp(self):
        m.TUNNELS.clear()

    def test_tunnel_start_and_stop_only_owned_forward(self):
        with patch.object(m,'forward_command') as call:
            m.tunnel_action('dev-backend','jboss-debug','start')
            self.assertEqual(call.call_args.args[1:],('forward','127.0.0.1:18787:127.0.0.1:8787'))
            m.tunnel_action('dev-backend','jboss-debug','stop')
            self.assertEqual(call.call_args.args[1:],('cancel','127.0.0.1:18787:127.0.0.1:8787'))
        self.assertFalse(m.TUNNELS)

    def test_duplicate_start_does_not_create_duplicate(self):
        with patch.object(m,'forward_command') as call:
            m.tunnel_action('dev-backend','jboss-debug','start')
            m.tunnel_action('dev-backend','jboss-debug','start')
            self.assertEqual(sum(c.args[1]=='forward' for c in call.call_args_list),1)

    def test_no_arbitrary_forward_or_action(self):
        with patch.object(m,'forward_command') as call:
            for name,action in [('127.0.0.1:22','start'),('jboss-debug','restart')]:
                with self.assertRaises(ValueError): m.tunnel_action('dev-backend',name,action)
            call.assert_not_called()

    def test_failed_bind_not_marked_active(self):
        with patch.object(m,'forward_command',side_effect=[None,RuntimeError('Address already in use')]):
            with self.assertRaises(RuntimeError): m.tunnel_action('dev-backend','jboss-debug','start')
        self.assertFalse(m.TUNNELS)

    def test_master_loss_clears_active_state(self):
        m.TUNNELS[('dev-backend','jboss-debug')]='spec'
        with patch.object(m,'forward_command',side_effect=RuntimeError('master gone')):
            entries=m.tunnel_list('dev-backend')
        self.assertTrue(all(not x['active'] for x in entries))

    def test_shutdown_cancels_owned_forwards(self):
        m.TUNNELS[('dev-backend','jboss-debug')]='spec'
        with patch.object(m,'forward_command') as call:
            m.close_tunnels()
            self.assertEqual(call.call_args.args[1:],('cancel','spec'))
        self.assertFalse(m.TUNNELS)

    def test_discovery_filters_names_and_unrelated_services(self):
        h=dict(H,discoverServices=True)
        with patch.object(m,'remote',return_value='tomcat.service enabled\nnginx.service enabled\nsshd.service enabled\nbad;cmd.service enabled\n'):
            self.assertEqual(m.service_names(h),['nginx.service','tomcat.service'])

    def test_discovered_logs_reject_unknown_units(self):
        h=dict(H,discoverServices=True)
        with patch.object(m,'remote',return_value='tomcat.service enabled\n') as call:
            with self.assertRaises(ValueError): m.logs(h,'sshd.service')
            self.assertEqual(call.call_count,1)

    def test_snapshot_preserves_exited_state(self):
        raw='\n@@IDENTITY\ncore\nup 1 day\n@@CPU\ncpu 10 2 3 40 5 0 0 0\n@@MEMORY\nMemTotal: 1000 kB\nMemAvailable: 400 kB\n@@DISK\nFilesystem 1024-blocks Used Available Capacity Mounted on\n/dev/sda 100 20 80 20% /\n@@SERVICES\nId=netwin-jboss.service\nActiveState=active\nSubState=exited\nMainPID=0\n\nId=netwin_backend.service\nActiveState=active\nSubState=running\nMainPID=123\n@@END\n'
        with patch.object(m,'remote',return_value=raw):
            s=m.snapshot(H)
        self.assertEqual(s['memoryPercent'],60)
        self.assertEqual(s['diskPercent'],20)
        self.assertEqual(s['services'][0]['SubState'],'exited')
        self.assertEqual(s['services'][1]['MainPID'],'123')
    def test_arbitrary_log_command_rejected(self):
        with patch.object(m,'remote') as call:
            with self.assertRaises(ValueError): m.logs(H,'x; reboot')
            call.assert_not_called()
    def test_nginx_failure_is_preserved(self):
        with patch.object(m,'remote',return_value='# comment\nnginx_up 0\nx NaN\n'):
            s=m.metrics(H,'nginx')
        self.assertEqual(s['samples'],[{'name':'nginx_up','value':0.0}])
    def test_socket_path_fits_macos(self):
        # Includes OpenSSH hash and temporary listener suffix.
        self.assertLess(len(str(m.SSH_DIR))+1+40+1+16,104)

    def test_ssh_is_noninteractive_and_strict(self):
        args=m.ssh_args(H)
        self.assertIn('BatchMode=yes',args)
        self.assertIn('StrictHostKeyChecking=yes',args)
    def test_timeout_becomes_clear_error(self):
        with patch.object(m.subprocess,'run',side_effect=subprocess.TimeoutExpired('ssh',15)):
            with self.assertRaisesRegex(RuntimeError,'15 segundos'): m.remote(H,'hostname')
    def test_failure_does_not_become_zero_metrics(self):
        with patch.object(m.subprocess,'run',return_value=subprocess.CompletedProcess('ssh',255,'','Permission denied')):
            with self.assertRaisesRegex(RuntimeError,'Permission denied'): m.snapshot(H)

if __name__=='__main__': unittest.main()
