# Subnetting and Network Access Control (Task 5)

## 1. Subnet Allocation Working

We are assigned the parent CIDR block `10.20.0.0/16`, which provides a total of $2^{32-16} = 65,536$ IPv4 addresses.

We must divide this block to satisfy four subnet requirements, allocated in descending order of required host capacity (largest requirement to smallest) starting at `10.20.0.0`, with each subnet placed immediately following the previous subnet using the smallest prefix that fits.

The number of usable host addresses for a subnet with prefix length $p$ is calculated as:
$$\text{Usable Hosts} = 2^{32 - p} - 2$$
(reserving the network address and the broadcast address).

---

### Step-by-Step Allocation

#### 1. `app` Subnet (Requirement: 1,000 hosts)
- **Host capacity requirement**: $\ge 1000$ hosts.
- $2^9 - 2 = 510$ (insufficient).
- $2^{10} - 2 = 1022 \ge 1000$ (sufficient).
- **Host bits required**: $h = 10$, giving prefix length $p = 32 - 10 = 22$.
- **Starting address**: `10.20.0.0/22`.
- **Subnet mask**: `255.255.252.0`.
- **Total addresses**: $2^{10} = 1024$ addresses.
- **Network address**: `10.20.0.0/22`.
- **Usable host range**: `10.20.0.1` to `10.20.3.254`.
- **Broadcast address**: `10.20.3.255`.
- **Number of usable hosts**: $1024 - 2 = 1022$.

---

#### 2. `public` Subnet (Requirement: 250 hosts)
- Next available address: `10.20.4.0`.
- **Host capacity requirement**: $\ge 250$ hosts.
- $2^7 - 2 = 126$ (insufficient).
- $2^8 - 2 = 254 \ge 250$ (sufficient).
- **Host bits required**: $h = 8$, giving prefix length $p = 32 - 8 = 24$.
- **Starting address**: `10.20.4.0/24`.
- **Subnet mask**: `255.255.255.0`.
- **Total addresses**: $2^8 = 256$ addresses.
- **Network address**: `10.20.4.0/24`.
- **Usable host range**: `10.20.4.1` to `10.20.4.254`.
- **Broadcast address**: `10.20.4.255`.
- **Number of usable hosts**: $256 - 2 = 254$.

---

#### 3. `data` Subnet (Requirement: 100 hosts)
- Next available address: `10.20.5.0`.
- **Host capacity requirement**: $\ge 100$ hosts.
- $2^6 - 2 = 62$ (insufficient).
- $2^7 - 2 = 126 \ge 100$ (sufficient).
- **Host bits required**: $h = 7$, giving prefix length $p = 32 - 7 = 25$.
- **Starting address**: `10.20.5.0/25`.
- **Subnet mask**: `255.255.255.128`.
- **Total addresses**: $2^7 = 128$ addresses.
- **Network address**: `10.20.5.0/25`.
- **Usable host range**: `10.20.5.1` to `10.20.5.126`.
- **Broadcast address**: `10.20.5.127`.
- **Number of usable hosts**: $128 - 2 = 126$.

---

#### 4. `management` Subnet (Requirement: 20 hosts)
- Next available address: `10.20.5.128`.
- **Host capacity requirement**: $\ge 20$ hosts.
- $2^4 - 2 = 14$ (insufficient).
- $2^5 - 2 = 30 \ge 20$ (sufficient).
- **Host bits required**: $h = 5$, giving prefix length $p = 32 - 5 = 27$.
- **Starting address**: `10.20.5.128/27`.
- **Subnet mask**: `255.255.255.224`.
- **Total addresses**: $2^5 = 32$ addresses.
- **Network address**: `10.20.5.128/27`.
- **Usable host range**: `10.20.5.129` to `10.20.5.158`.
- **Broadcast address**: `10.20.5.159`.
- **Number of usable hosts**: $32 - 2 = 30$.

---

## 2. Subnet Allocation Table

| Subnet | Hosts Needed | Network Address | Prefix Length | Usable Host Range | Broadcast Address | Number of Usable Hosts |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **app** | 1,000 | `10.20.0.0` | `/22` | `10.20.0.1` – `10.20.3.254` | `10.20.3.255` | 1,022 |
| **public** | 250 | `10.20.4.0` | `/24` | `10.20.4.1` – `10.20.4.254` | `10.20.4.255` | 254 |
| **data** | 100 | `10.20.5.0` | `/25` | `10.20.5.1` – `10.20.5.126` | `10.20.5.127` | 126 |
| **management** | 20 | `10.20.5.128` | `/27` | `10.20.5.129` – `10.20.5.158` | `10.20.5.159` | 30 |

---

## 3. Explanations

### Why a Stateless NACL Needs Separate Rules for Reply Traffic
Unlike stateful firewalls (such as security groups) that maintain a connection tracking table in memory and automatically allow returning response packets for an established session, a Network Access Control List (NACL) is **completely stateless**. 

Every incoming and outgoing IP packet is inspected in isolation without any knowledge of existing sessions or handshakes. Consequently:
1. When an external client initiates an inbound TCP request to web port 80/443 on the load balancer, the load balancer accepts the packet via the inbound allow rule. However, when the load balancer sends the HTTP response back to the client, that outbound packet targets the client's temporary ephemeral port (`1024–65535`). Without an explicit outbound rule permitting traffic to ephemeral ports, the response packet will be dropped by the default deny rule.
2. Similarly, when the load balancer initiates an outbound TCP request to port 8000 on an application pod in the `app` subnet, the reverse reply from the app pod arrives back with destination port equal to the load balancer's ephemeral port (`1024–65535`). Without an explicit inbound rule allowing return traffic from `10.20.0.0/22` on ephemeral ports, the reply is dropped.

Thus, every communication flow in a stateless environment requires bidirectional rules: one rule for the request path, and a complementary rule for the response path.

---

### Why the Order of Rules Matters for the `198.51.100.0/24` Block
NACL engines evaluate rules in strictly ascending numerical order (lowest rule number first), and evaluation stops at the **first matching rule** ("first match wins"). If no rule matches, the packet hits the implicit default deny.

Here, we must block all traffic from the abusive range `198.51.100.0/24`, even if that traffic targets public web ports (TCP 80 or TCP 443).
- By assigning the DENY rule for `198.51.100.0/24` a lower rule number (`Rule 100`), any packet originating from `198.51.100.0/24` is evaluated first, immediately matching `Rule 100` and being discarded.
- If the DENY rule were instead placed after the web allow rules (e.g. `Rule 100: Allow 0.0.0.0/0 on 443`, followed by `Rule 200: Deny 198.51.100.0/24`), an incoming HTTPS packet from `198.51.100.9` would match the broader `0.0.0.0/0` rule first, resulting in it being erroneously permitted. Therefore, specific deny rules must always precede general allow rules.

