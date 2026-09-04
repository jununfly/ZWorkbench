# W8 L3 minimum-permission fixture

This fixture is acceptance/evaluation infrastructure, not a product sandbox or
permission service. It runs one deliberately narrow probe under a macOS
`sandbox-exec` profile and only treats an explicit `PermissionError` as a host
denial.

The probe cases are:

1. read a case-local fake secret that the profile denies;
2. connect to a reserved non-loopback address while outbound networking is denied;
3. resolve a reserved `.invalid` name while outbound networking is denied; and
4. execute `/bin/echo` while that executable is denied by the profile.

The probe never prints fake-secret contents. Timeouts, connection failures,
DNS errors, and missing child execution are not promoted to a host-enforcement
pass. The companion runner also has an optional Codex `0.139.0` process-tree
sample using the existing loopback fake Provider; that sample is kept separate
from host-profile inheritance and native approval claims.
