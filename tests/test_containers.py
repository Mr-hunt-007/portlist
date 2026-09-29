"""Container port ownership must not turn ambiguity into a name or badge."""
from plcore import containers


def container(cid, port, state="running", ports=None):
    return {"id": cid, "name": "box-" + cid, "engine": "docker", "state": state,
            "ports": ports if ports is not None else [{"host_port": port, "host_ip": "0.0.0.0",
                                                       "proto": "tcp"}]}


def test_by_port_omits_ambiguous_distinct_running_publishers():
    first = container("one", 80)
    second = container("two", 80)
    third = container("three", 443)
    doc = {"reachable": True, "containers": [first, second, third]}
    assert set(containers.by_port(doc)) == {443}
    assert containers.by_port(doc)[443]["id"] == "three"
    assert not containers.by_port({"containers": list(reversed(doc["containers"]))}).get(80)


def test_distinct_tcp_owners_on_different_host_addresses_are_ambiguous():
    loopback = container("local", 8080, ports=[{"host_port": 8080, "host_ip": "127.0.0.1", "proto": "tcp"}])
    lan = container("lan", 8080, ports=[{"host_port": 8080, "host_ip": "192.168.1.4", "proto": "tcp"}])
    for ordered in ([loopback, lan], [lan, loopback]):
        assert 8080 not in containers.by_port({"containers": ordered})


def test_by_port_keeps_one_container_with_duplicate_host_bindings():
    same = container("one", 80, ports=[{"host_port": 80, "host_ip": "0.0.0.0", "proto": "tcp"},
                                       {"host_port": 80, "host_ip": "::", "proto": "tcp"}])
    duplicate = dict(same, ports=[{"host_port": 80, "host_ip": "127.0.0.1", "proto": "tcp"}])
    stopped = container("not-running", 80, state="exited")
    table = containers.by_port({"containers": [same, duplicate, stopped]})
    assert table[80]["id"] == "one"
    assert table[80]["published"] == same["ports"][0]


def test_by_port_needs_running_owner_and_does_not_use_name_as_identity():
    a = container("", 80)
    b = container("", 80)
    assert 80 not in containers.by_port({"containers": [a, b]})
    assert containers.by_port({"containers": [container("one", 80, "stopped")]}) == {}


def test_by_port_does_not_attribute_udp_or_unlabelled_publishers_to_tcp():
    udp = container("dns-udp", 53, ports=[{"host_port": 53, "proto": "udp"}])
    unlabelled = container("no-protocol", 54, ports=[{"host_port": 54}])
    unexpected = container("unsupported", 55, ports=[{"host_port": 55, "proto": "sctp"}])
    assert containers.by_port({"containers": [udp, unlabelled, unexpected]}) == {}


def test_udp_on_same_number_does_not_hide_unique_tcp_owner():
    udp = container("dns-udp", 53, ports=[{"host_port": 53, "proto": "udp"}])
    tcp = container("dns-tcp", 53)
    for ordered in ([udp, tcp], [tcp, udp]):
        mapped = containers.by_port({"containers": ordered})
        assert set(mapped) == {53}
        assert mapped[53]["id"] == "dns-tcp"
        assert mapped[53]["published"]["proto"] == "tcp"
