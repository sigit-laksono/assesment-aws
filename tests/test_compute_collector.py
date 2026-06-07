"""
Property-based tests for collectors/compute.py
Feature: compute-collector-enhancement
"""
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Helper Strategies
# ---------------------------------------------------------------------------


def tag_entry_strategy():
    """Generate a single AWS tag {Key: ..., Value: ...}"""
    return st.fixed_dictionaries({
        'Key': st.sampled_from(['Name', 'Environment', 'Env', 'Team', 'CostCenter', 'Project']),
        'Value': st.text(min_size=1, max_size=50),
    })


def tag_combination_strategy():
    """Generate tag lists specifically designed to test environment priority logic."""
    return st.one_of(
        st.just([]),  # No tags
        st.just([{'Key': 'Name', 'Value': 'test-server'}]),  # Only Name
        st.just([{'Key': 'Environment', 'Value': 'production'}]),  # Only Environment
        st.just([{'Key': 'Env', 'Value': 'staging'}]),  # Only Env
        st.just([{'Key': 'Environment', 'Value': 'prod'}, {'Key': 'Env', 'Value': 'dev'}]),  # Both — Environment wins
        st.lists(tag_entry_strategy(), min_size=0, max_size=10),  # Random
    )


def ec2_instance_strategy():
    """Generate random EC2 instance dicts with varying optional fields."""
    base = st.fixed_dictionaries({
        'InstanceId': st.text(alphabet='abcdef0123456789', min_size=8, max_size=17).map(lambda s: f'i-{s}'),
        'InstanceType': st.sampled_from(['t3.micro', 't3.small', 'm5.large', 'c6g.xlarge']),
        'State': st.fixed_dictionaries({'Name': st.sampled_from(['running', 'stopped', 'terminated'])}),
        'LaunchTime': st.datetimes(min_value=datetime(2020, 1, 1), max_value=datetime(2026, 1, 1)),
        'Placement': st.fixed_dictionaries({
            'AvailabilityZone': st.sampled_from(['us-east-1a', 'us-east-1b', 'eu-west-1c', 'ap-southeast-1a'])
        }),
    })

    optional_fields = st.fixed_dictionaries({
        'Platform': st.one_of(st.none(), st.just('Windows')),
        'Architecture': st.one_of(st.none(), st.sampled_from(['x86_64', 'arm64'])),
        'VpcId': st.one_of(st.none(), st.text(alphabet='abcdef0123456789', min_size=5, max_size=12).map(lambda s: f'vpc-{s}')),
        'SubnetId': st.one_of(st.none(), st.text(alphabet='abcdef0123456789', min_size=5, max_size=12).map(lambda s: f'subnet-{s}')),
        'PublicIpAddress': st.one_of(
            st.none(),
            st.tuples(
                st.integers(1, 255), st.integers(0, 255),
                st.integers(0, 255), st.integers(0, 255)
            ).map(lambda t: f'{t[0]}.{t[1]}.{t[2]}.{t[3]}')
        ),
        'EbsOptimized': st.one_of(st.none(), st.booleans()),
        'Tags': st.one_of(st.none(), st.lists(tag_entry_strategy(), min_size=0, max_size=10)),
    })

    @st.composite
    def build_instance(draw):
        b = draw(base)
        opts = draw(optional_fields)
        # Merge base and optional, removing None values (simulates absent keys)
        instance = dict(b)
        for key, val in opts.items():
            if val is not None:
                instance[key] = val
        return instance

    return build_instance()


# ---------------------------------------------------------------------------
# Unit Tests: EC2 Edge Cases (Task 5.1)
# ---------------------------------------------------------------------------


def _make_assessment_data():
    """Create a fresh assessment_data dict for testing."""
    return {'services': {}}


def _make_mock_session(instances=None, load_balancers=None, listeners_resp=None, listeners_error=None):
    """Create a mock boto3 session with configurable EC2/ELBv2 responses."""
    session = MagicMock()

    # EC2 mock
    ec2_client = MagicMock()
    ec2_paginator = MagicMock()
    ec2_paginator.paginate.return_value = [
        {'Reservations': [{'Instances': instances or []}]}
    ]
    ec2_client.get_paginator.return_value = ec2_paginator
    
    # ELBv2 mock
    elbv2_client = MagicMock()
    elbv2_paginator = MagicMock()
    elbv2_paginator.paginate.return_value = [
        {'LoadBalancers': load_balancers or []}
    ]
    elbv2_client.get_paginator.return_value = elbv2_paginator

    if listeners_error:
        elbv2_client.describe_listeners.side_effect = listeners_error
    elif listeners_resp is not None:
        elbv2_client.describe_listeners.return_value = listeners_resp

    def client_factory(service_name):
        if service_name == 'ec2':
            return ec2_client
        elif service_name == 'elbv2':
            return elbv2_client
        return MagicMock()

    session.client.side_effect = client_factory
    return session


class TestEC2EdgeCases:
    """Unit tests for EC2 field extraction edge cases."""

    def test_ec2_all_fields_present(self):
        """EC2 with all fields present — verify semua field terextract benar."""
        instance = {
            'InstanceId': 'i-abc123def456',
            'InstanceType': 'm5.large',
            'State': {'Name': 'running'},
            'LaunchTime': datetime(2024, 6, 15, 10, 30, 0),
            'Placement': {'AvailabilityZone': 'ap-southeast-1a'},
            'Platform': 'Windows',
            'Architecture': 'x86_64',
            'VpcId': 'vpc-12345',
            'SubnetId': 'subnet-67890',
            'PublicIpAddress': '54.123.45.67',
            'EbsOptimized': True,
            'Tags': [
                {'Key': 'Name', 'Value': 'production-web'},
                {'Key': 'Environment', 'Value': 'production'},
            ],
        }

        session = _make_mock_session(instances=[instance])
        data = _make_assessment_data()

        from collectors.compute import inventory_ec2
        result = inventory_ec2(session, data)

        assert result is True
        instances = data['services']['ec2']['instances']
        assert len(instances) == 1
        i = instances[0]

        # Existing fields
        assert i['id'] == 'i-abc123def456'
        assert i['type'] == 'm5.large'
        assert i['state'] == 'running'
        assert i['launch_time'] == '2024-06-15 10:30:00'

        # New fields
        assert i['platform'] == 'Windows'
        assert i['architecture'] == 'x86_64'
        assert i['availability_zone'] == 'ap-southeast-1a'
        assert i['vpc_id'] == 'vpc-12345'
        assert i['subnet_id'] == 'subnet-67890'
        assert i['public_ip'] == '54.123.45.67'
        assert i['ebs_optimized'] is True
        assert i['name'] == 'production-web'
        assert i['environment'] == 'production'

    def test_ec2_minimal_fields_only(self):
        """EC2 with minimal fields only — verify semua defaults terisi."""
        instance = {
            'InstanceId': 'i-minimal001',
            'InstanceType': 't3.micro',
            'State': {'Name': 'stopped'},
            'LaunchTime': datetime(2023, 1, 1, 0, 0, 0),
            'Placement': {'AvailabilityZone': 'us-east-1a'},
        }

        session = _make_mock_session(instances=[instance])
        data = _make_assessment_data()

        from collectors.compute import inventory_ec2
        result = inventory_ec2(session, data)

        assert result is True
        i = data['services']['ec2']['instances'][0]

        assert i['platform'] == 'Linux'
        assert i['architecture'] == ''
        assert i['vpc_id'] == ''
        assert i['subnet_id'] == ''
        assert i['public_ip'] is None
        assert i['ebs_optimized'] is False
        assert i['name'] == ''
        assert i['environment'] == ''

    def test_ec2_with_windows_platform(self):
        """EC2 with Platform='Windows' — verify platform = 'Windows'."""
        instance = {
            'InstanceId': 'i-windows001',
            'InstanceType': 'm5.xlarge',
            'State': {'Name': 'running'},
            'LaunchTime': datetime(2024, 3, 10, 8, 0, 0),
            'Placement': {'AvailabilityZone': 'eu-west-1c'},
            'Platform': 'Windows',
        }

        session = _make_mock_session(instances=[instance])
        data = _make_assessment_data()

        from collectors.compute import inventory_ec2
        inventory_ec2(session, data)

        i = data['services']['ec2']['instances'][0]
        assert i['platform'] == 'Windows'

    def test_ec2_with_no_tags_key(self):
        """EC2 with no Tags key — verify name = '', environment = ''."""
        instance = {
            'InstanceId': 'i-notags001',
            'InstanceType': 't3.small',
            'State': {'Name': 'running'},
            'LaunchTime': datetime(2024, 5, 20, 12, 0, 0),
            'Placement': {'AvailabilityZone': 'us-east-1b'},
        }
        # No 'Tags' key at all

        session = _make_mock_session(instances=[instance])
        data = _make_assessment_data()

        from collectors.compute import inventory_ec2
        inventory_ec2(session, data)

        i = data['services']['ec2']['instances'][0]
        assert i['name'] == ''
        assert i['environment'] == ''

    def test_ec2_environment_and_env_tags_priority(self):
        """EC2 with Environment dan Env tags — verify Environment takes priority."""
        instance = {
            'InstanceId': 'i-envpriority',
            'InstanceType': 't3.micro',
            'State': {'Name': 'running'},
            'LaunchTime': datetime(2024, 4, 1, 0, 0, 0),
            'Placement': {'AvailabilityZone': 'us-east-1a'},
            'Tags': [
                {'Key': 'Environment', 'Value': 'production'},
                {'Key': 'Env', 'Value': 'dev'},
            ],
        }

        session = _make_mock_session(instances=[instance])
        data = _make_assessment_data()

        from collectors.compute import inventory_ec2
        inventory_ec2(session, data)

        i = data['services']['ec2']['instances'][0]
        # Environment takes priority over Env
        assert i['environment'] == 'production'

    def test_ec2_only_env_tag_fallback(self):
        """EC2 with only Env tag (no Environment) — verify fallback to Env."""
        instance = {
            'InstanceId': 'i-envfallback',
            'InstanceType': 't3.micro',
            'State': {'Name': 'running'},
            'LaunchTime': datetime(2024, 4, 1, 0, 0, 0),
            'Placement': {'AvailabilityZone': 'us-east-1a'},
            'Tags': [
                {'Key': 'Env', 'Value': 'staging'},
            ],
        }

        session = _make_mock_session(instances=[instance])
        data = _make_assessment_data()

        from collectors.compute import inventory_ec2
        inventory_ec2(session, data)

        i = data['services']['ec2']['instances'][0]
        assert i['environment'] == 'staging'


# ---------------------------------------------------------------------------
# Unit Tests: ALB Edge Cases (Task 5.2)
# ---------------------------------------------------------------------------


class TestALBEdgeCases:
    """Unit tests for ALB listener count edge cases."""

    def _make_alb(self, name='test-alb', arn='arn:aws:elasticloadbalancing:us-east-1:123456789:loadbalancer/app/test/abc'):
        return {
            'LoadBalancerName': name,
            'LoadBalancerArn': arn,
            'DNSName': f'{name}.us-east-1.elb.amazonaws.com',
            'Scheme': 'internet-facing',
            'State': {'Code': 'active'},
            'VpcId': 'vpc-alb123',
            'Type': 'application',
            'AvailabilityZones': [
                {'ZoneName': 'us-east-1a'},
                {'ZoneName': 'us-east-1b'},
            ],
        }

    def test_alb_successful_describe_listeners(self):
        """ALB with successful describe_listeners — verify correct count."""
        alb = self._make_alb()
        listeners_resp = {
            'Listeners': [
                {'ListenerArn': 'arn:listener:1', 'Port': 80},
                {'ListenerArn': 'arn:listener:2', 'Port': 443},
            ]
        }

        session = _make_mock_session(load_balancers=[alb], listeners_resp=listeners_resp)
        data = _make_assessment_data()

        from collectors.compute import inventory_alb
        result = inventory_alb(session, data)

        assert result is True
        lbs = data['services']['alb']['load_balancers']
        assert len(lbs) == 1
        assert lbs[0]['listener_count'] == 2
        # Existing fields unchanged
        assert lbs[0]['name'] == 'test-alb'
        assert lbs[0]['scheme'] == 'internet-facing'
        assert lbs[0]['state'] == 'active'

    def test_alb_failed_describe_listeners(self):
        """ALB with failed describe_listeners — verify listener_count = 0 and collection continues."""
        alb = self._make_alb()

        session = _make_mock_session(
            load_balancers=[alb],
            listeners_error=Exception("Access Denied")
        )
        data = _make_assessment_data()

        from collectors.compute import inventory_alb
        result = inventory_alb(session, data)

        assert result is True
        lbs = data['services']['alb']['load_balancers']
        assert len(lbs) == 1
        assert lbs[0]['listener_count'] == 0

    def test_multiple_albs_mixed_success_failure(self):
        """Multiple ALBs with mixed success/failure — verify partial failures don't affect others."""
        alb1 = self._make_alb(name='alb-success', arn='arn:alb:1')
        alb2 = self._make_alb(name='alb-failure', arn='arn:alb:2')
        alb3 = self._make_alb(name='alb-success2', arn='arn:alb:3')

        # describe_listeners succeeds for alb1 and alb3, fails for alb2
        call_count = [0]

        def mock_describe_listeners(**kwargs):
            call_count[0] += 1
            arn = kwargs.get('LoadBalancerArn', '')
            if arn == 'arn:alb:2':
                raise Exception("Throttling")
            return {'Listeners': [{'ListenerArn': f'arn:listener:{call_count[0]}', 'Port': 80}]}

        session = _make_mock_session(load_balancers=[alb1, alb2, alb3])
        # Override describe_listeners with custom side_effect
        elbv2_client = session.client('elbv2')
        elbv2_client.describe_listeners.side_effect = mock_describe_listeners

        data = _make_assessment_data()

        from collectors.compute import inventory_alb
        result = inventory_alb(session, data)

        assert result is True
        lbs = data['services']['alb']['load_balancers']
        assert len(lbs) == 3

        # alb-success: listener_count = 1
        assert lbs[0]['name'] == 'alb-success'
        assert lbs[0]['listener_count'] == 1

        # alb-failure: listener_count = 0 (error)
        assert lbs[1]['name'] == 'alb-failure'
        assert lbs[1]['listener_count'] == 0

        # alb-success2: listener_count = 1
        assert lbs[2]['name'] == 'alb-success2'
        assert lbs[2]['listener_count'] == 1
