# Platform implementation runbook

This is a proposed 10-seat café topology. Match interface names, addresses and equipment features to your actual lab before applying configuration. The app alone does not create VLANs, change IP addresses, monitor antivirus, or lock PCs.

## Address and switch plan

| VLAN | Purpose | Subnet / gateway | Allocation |
|---|---|---|---|
| 10 | Management | 192.168.10.0/24 / .1 | Switch .2; AP .3; host .5; application VM .10; cashier .20; printer .30 |
| 20 | Customer PCs | 192.168.20.0/24 / .1 | DHCP reservations .101-.110 for PC01-PC10; exclude reservations from dynamic allocation |
| 30 | Guest Wi-Fi | 192.168.30.0/24 / .1 | DHCP .100-.199; wireless client isolation |

Use each VLAN's .1 router interface for DNS forwarding and DHCP. Router WAN uses the ISP assignment; NAT provides Internet access. No inbound WAN port forwarding to NOIR, SSH or MySQL.

Managed switch: port 1 tagged trunk VLANs 10/20/30 to router; ports 2-11 untagged access VLAN20 for PCs; port12 cashier VLAN10; port13 host VLAN10; port14 printer VLAN10; port15 tagged VLAN10/30 to AP (configure the AP management VLAN10 explicitly); ports16-24 disabled until needed. On trunks use matching tagging at both ends; disable unused native VLAN access where equipment permits. A 24-port switch leaves nine unused ports, allowing expansion to 19 customer PCs with this layout. A full 20-seat layout needs one additional switch port or a larger switch because 15 existing ports plus 10 additional PCs equals 25.

Configure DHCP reservations on the router using each device's actual MAC, then verify its lease on the PC. Enter the confirmed address under **Admin → Inventory → Edit device → IPv4 address**. Use NOIR-PC-01 through NOIR-PC-10 hostnames; NOIR-CASHIER; NOIR-HOST; NOIR-APP. Never invent real MAC addresses in inventory.

## Router/firewall rule order

1. Allow established/related return traffic.
2. Allow DHCP and DNS only to the appropriate router interface; block customer/guest access to router administration. Administer router/switch/AP only from cashier .10.20.
3. Allow customer VLAN20 to application VM 192.168.10.10 TCP443.
4. Allow cashier 192.168.10.20 to VM TCP443 and SSH TCP22; allow cashier SSH to host 192.168.10.5. Allow cashier to printer on its chosen print protocol only (prefer IPP TCP631 if supported).
5. Deny customer and guest traffic to all other private/internal subnets. Guest VLAN30 has no access to NOIR. Deny unnecessary lateral traffic with host firewalls; same-VLAN traffic does not necessarily traverse the router. Enable switch port isolation for customer access ports if supported and test it.
6. Permit Internet access according to café policy. Cap guest bandwidth and test fair use; the initial 300 Mbps service tier is a planning choice, not a speed measurement.
7. Deny other inter-VLAN traffic and log useful denies. Mirror equivalent policy for IPv6, or disable IPv6 in the lab until it has an approved firewall plan; IPv4 rules alone do not secure IPv6.

Exact router commands depend on the model. Capture VLAN, DHCP and firewall screenshots from the actual device or simulator. No Packet Tracer file is claimed; the supplied editable Draw.io topology is the network design deliverable.

## Windows 11 Pro client installation

1. Confirm hardware compatibility, BIOS support for the selected CPU, TPM2, UEFI Secure Boot, and authorized licensing. The report budgets separate retail Windows licenses; confirm Internet café/public-use licensing terms with your supplier before procurement.
2. Install Windows 11 Pro 25H2 or a supported, tested later release from official media. Record the exact edition/build used. Update the OS and OEM drivers.
3. Create a named maintenance administrator and a standard customer Windows account. Do not let the customer account install software or obtain administrator credentials. Application member/admin roles are separate from Windows accounts.
4. Turn on Defender antivirus and Windows Firewall; verify security intelligence updates. Use browser guest/private sessions and remove customer downloads after sign-out according to the café privacy policy. The web app does not perform Windows profile cleanup.
5. Use a protected administrator folder for reports and backups. Keep public temporary work in a separate folder; do not share the database or .env. Use separate print queues/permissions; customers request printing at the counter.
6. Obtain a DHCP lease/reservation, check the correct gateway and DNS, and test HTTPS to NOIR. Capture the OS build, account type, IP, firewall and antivirus evidence. `scripts/Collect-Evidence.ps1` gathers read-only checks and records unavailable checks honestly.

## Ubuntu 24.04 LTS host and VM

1. Install Ubuntu Server 24.04 LTS, enable CPU virtualization in firmware, apply updates, and create a named sudo administrator. Use SSH keys and a local recovery console. Keep the host for virtualization only.
2. Install KVM/libvirt using Ubuntu's official instructions. Configure a physical Linux bridge `br0` on the host NIC connected to switch port13 (access VLAN10). Put host address 192.168.10.5/24 on the bridge; gateway/DNS 192.168.10.1. Do not leave duplicate addressing on the physical NIC. Use local console while changing network settings.
3. Create NOIR-APP: 4vCPU, 8GB RAM, 100GB virtual disk, Ubuntu24.04, virtio disk/NIC, bridge br0; IP192.168.10.10/24. Keep its virtual disk on the host NVMe. Do not use the default NAT network if LAN clients must reach the VM directly.
4. Install Python3, venv support, MySQL8.x and Nginx in the VM. Check the actual MySQL version (Ubuntu24.04's repository and an optional upstream8.4 repository can differ). Use the same tested major version for backups/restores. Copy NOIR to `/opt/noir`, create its venv, and follow README.md to initialize the database and create the first administrator.
5. Bind MySQL to loopback; the application uses DB_HOST=127.0.0.1. After installation/migration, restrict the runtime database user to SELECT, INSERT, UPDATE, DELETE; temporarily use a separate migration account with CREATE, ALTER, INDEX, REFERENCES for future upgrades. Never run the application as MySQL root.
6. Run the app under an unprivileged Linux account through systemd; keep Waitress at 127.0.0.1:8000. Nginx serves HTTPS443 for `noir.cafe.test`, with internal DNS pointing to .10.10. Install a certificate from your trusted internal CA with that hostname and install the CA trust on managed clients; do not tell users to bypass certificate warnings. Templates are in deployment/.
7. Set COOKIE_SECURE=true and TRUSTED_HOSTS=noir.cafe.test,localhost,127.0.0.1 only after HTTPS is working. Secure cookies will not work over ordinary HTTP. For localhost-only development, keep COOKIE_SECURE=false.
8. On the app VM, review then apply UFW: default deny incoming; allow TCP22 from 192.168.10.20; allow TCP443 from 192.168.10.20 and 192.168.20.0/24. Do not open port3306 or8000. Before enabling, keep local console access and confirm the SSH rule. On the host allow management SSH only from .10.20 and validate bridged guest traffic separately.
9. Create a separate temporary restore VM: 2vCPU, 4GB, 100GB disk, isolated virtual network. Use it for restore drills; do not attach it to the café VLAN. Snapshots help rollback a planned change but do not replace offline database backups.

## Acceptance evidence

Demonstrate correct and denied connections, reboot persistence, admin/member permissions, a timed session and invoice, a saved device/repair record, CSV export, and a successful isolated restore. Measure dashboard response time and resource usage with ten clients. The included verification file distinguishes completed automated checks from these outstanding site checks.
