# A42364 Candidate Cost Ledger

Active protocol remains **8 SQL / 12 commands / 2 seconds**; dynamic bootstrap
exceeds it and remains BLOCKED. Candidate: **12 SQL / 32 commands / 30 seconds**,
version a42364.bootstrap-candidate.v3; unsigned, unmeasured, never activated.
No reset/refund/retry is permitted on unknown ACK.

The following canonical model plan is reproducible from
cost_plan(FixtureIdentity.derive(scope, installation)). Identity is a public offline
test vector, NOT an installed fixture, image digest or approval.
Fresh model plan hash: `4956469f491eb75316f60dc7dc6affc84b1991b57df360d226a5d48ba4024103`.
Prebuilt model plan hash: `765d475359987c83cbf447dd27e6ceca9832d52d4c581b176cb6537508c1b694`.
Real approval must hash its own exact reviewed installation/scope plan.

## DAG and Raw Templates

Each operation declares after, kind, SQL/command cost, worst-case allocation and
SHA256 of the exact template. Allocations are paper reservations, NOT measurements.
OS labels describe operations, not unrestricted executable argv. Runtime adapters
construct fixed argv; root may not treat these labels as commands.

| Operation | Depends On | SQL | Commands | Allocation ms | Template SHA256 |
|---|---|---:|---:|---:|---|
| ROOT_VERIFY_PINNED_IMAGE | - | 0 | 1 | 1000 | e179269c6bf69e9361850699275a1ff7100288395ef0d7d866c1f6e7af4dea27 |
| ROOT_CREATE_CGROUP_SCOPE | ROOT_VERIFY_PINNED_IMAGE | 0 | 1 | 1000 | c6dda3a48ba28c7c2484bc021a7c758a2617ceaaf522ecaf24ca692186cdbf59 |
| ROOT_BIND_PRIVATE_SOCKET | ROOT_CREATE_CGROUP_SCOPE | 0 | 1 | 1000 | d29f25934f42de9ee400316644043bbe882c95938e1b5fec2dd3a7aee55502f3 |
| ROOT_SEAL_CREDENTIALS | ROOT_BIND_PRIVATE_SOCKET | 0 | 1 | 1000 | 02f82056d4b3349b57d98d2b7c7fe64b7bf4200b534a0c1500d4138f7774cbc2 |
| C_VOLUME_CREATE | ROOT_SEAL_CREDENTIALS | 0 | 1 | 1000 | 65111d1b2722ba8dee8f6bc704c1b0159567c2edbbeaecac0542a8965cc46aab |
| C_VOLUME_INSPECT | C_VOLUME_CREATE | 0 | 1 | 1000 | 8e4e1ae18fdf82debfb5dfd4b29c5923a1b50c33d7e7fcf64b4e3221de564dfc |
| C_SECRET_CREATE | C_VOLUME_INSPECT | 0 | 1 | 1000 | d4edab2a4b8988d86d1446ec03649a4d41cf9806756ad59d13be236e30b50139 |
| C_SECRET_INSPECT | C_SECRET_CREATE | 0 | 1 | 1000 | 3af69ed1c0bf0466a5d947c537e5bb0f9cf5a27e052db14c79ce53fc017338ff |
| C_CONTAINER_CREATE | C_SECRET_INSPECT | 0 | 1 | 1000 | cb3fc7b16f00dfea9f89038508427d425929a5084bf4774564702ff5573d1923 |
| C_CONTAINER_INSPECT | C_CONTAINER_CREATE | 0 | 1 | 1000 | dc3c8b940a83fca496f6b6c985b4a50f92b7133d1f7a967584f2e487543418bb |
| C_PREPARED_INSPECT | C_CONTAINER_INSPECT | 0 | 1 | 1000 | 2f5992d8a48902247cd46b5b790ee47bb91524c192282781018689badfaff480 |
| C_BEFORE_START_INSPECT | C_PREPARED_INSPECT | 0 | 1 | 1000 | ba50f121e6efdf2e0cd6c0c6814817f1fe5432811aa47da12f40ffe59390e2e8 |
| C_START | C_BEFORE_START_INSPECT | 0 | 1 | 1000 | 6e0db18050c1fd12ceb1b6a0d9d412dd4a0a675f76eedcf60137058a538a96c1 |
| IMAGE_INITDB | C_START | 0 | 1 | 1000 | 14bac72d54e8a7580e55e9e71e2533b04441a6c8f9399e540b2410fe0732bd3d |
| IMAGE_WRITE_PG_HBA | IMAGE_INITDB | 0 | 1 | 1000 | d6007f356f8c92781335b979ff7bb04d8f01429c990ba2cb2b49424135a36f21 |
| IMAGE_POSTGRES_START | IMAGE_WRITE_PG_HBA | 0 | 1 | 1000 | 0814320c24a939167acba7df5389322598a0606582a812ce6dd847636acc6218 |
| C_RUNNING_INSPECT | IMAGE_POSTGRES_START | 0 | 1 | 1000 | 3f3a4e317b554c352e672a5e609a78d109edca27cebc53f12b39be021c48b567 |
| C_READINESS_INSPECT | C_RUNNING_INSPECT | 0 | 1 | 1000 | 9d1e575540360ae66d47c9cd09fa3e737971193b093fde00ffec537946ed9f4e |
| O_BEFORE_VOLUME_INSPECT | C_READINESS_INSPECT | 0 | 1 | 1000 | e7dd800608798b9bc3ce8abaf1c70dd694c6f7ab8b0be88394e2bcbd5bd24461 |
| O_BEFORE_SECRET_INSPECT | O_BEFORE_VOLUME_INSPECT | 0 | 1 | 1000 | 9af1731a0bae44d3c561e67892d0546da2f16a2cac4d8fd5d31dcd30c5159805 |
| O_BEFORE_CONTAINER_INSPECT | O_BEFORE_SECRET_INSPECT | 0 | 1 | 1000 | 0bddb35cddd16506a96a8e403f7c265aa471ed00db0ec5a87aee328345a17415 |
| OWNER_AUTH_CONNECT | O_BEFORE_CONTAINER_INSPECT | 0 | 1 | 1000 | d311bc97266fb4070035d2652a47e4b47935156d0df64ffbd0fd30f7ed765edf |
| CREATE_DATABASE | OWNER_AUTH_CONNECT | 1 | 0 | 100 | ddf129a900986b2f312cef1af115f70300eeab0d7c971f64011d41af8d4d0a6d |
| REVOKE_DATABASE | CREATE_DATABASE | 1 | 0 | 100 | 4f628b79d319c44ec61d64b7d85e7ba914667f45a1ab209c8e9fa303c53dda93 |
| REVOKE_SCHEMA | REVOKE_DATABASE | 1 | 0 | 100 | b55c75316fc0b413bd15a3d969578af208be40f3d388a6b3b390aa168575d8c4 |
| CREATE_PROBE_ROLE | REVOKE_SCHEMA | 1 | 0 | 100 | c8d3e3cef2fad6e54faa71883c6d4b5d732b44fd95aade950a856f6fb59511a5 |
| SET_SCRAM_VERIFIER | CREATE_PROBE_ROLE | 1 | 0 | 100 | def54802521bcc99cc55e5e2b7c639df4b19e2060bcf335c13391fd4475f26c8 |
| REVOKE_DEFAULT_FUNCTION | SET_SCRAM_VERIFIER | 1 | 0 | 100 | 036ef2cb5e6a4062d00df4ef56c634e9e3adb8b8466ad68410019b70c0d420cc |
| CONNECT_ONLY | REVOKE_DEFAULT_FUNCTION | 1 | 0 | 100 | 0d0b9404a7bb18cdab33b1982d274feeac282877c6510229490b2e89d2e763bc |
| READ_ONLY_DEFAULT | CONNECT_ONLY | 1 | 0 | 100 | 8f2e3ea1d890387e6e4245a1e6e0e865ec2485e2e3955bfbbcbf99623c3b4346 |
| TIMEOUT_DEFAULT | READ_ONLY_DEFAULT | 1 | 0 | 100 | 2e38ab9b42d610c21d48797f4be16279748ffa7d92c7a54ea79dce80bb0a8820 |
| RAW_OWNER_ROLE_AUDIT | TIMEOUT_DEFAULT | 1 | 0 | 100 | 0db1a500b3fc6d20e37d9c65bc76c16923b60bedd1b5b76382ee2bd105e708f0 |
| AUTH_CONFIG_AUDIT | RAW_OWNER_ROLE_AUDIT | 1 | 0 | 100 | a70e52f0d7dff49b535ce6f08ae6a738cd99dbcddf6b5c326a02c8625c78b49c |
| USER_OBJECT_PRIVILEGE_AUDIT | AUTH_CONFIG_AUDIT | 1 | 0 | 100 | 1b09437a6c7170cf8d4cd6bc48a2709ec2089f65867de537378978d824919df6 |
| PROBE_AUTH_CONNECT | USER_OBJECT_PRIVILEGE_AUDIT | 0 | 1 | 1000 | 267c0260d18e7c1d5fdbeca7c4a034cc328c4162073e4c6cd67d214456bc6673 |
| O_AFTER_VOLUME_INSPECT | PROBE_AUTH_CONNECT | 0 | 1 | 1000 | d61aabf6cca8c5bbdf0aa659668df8b3d92bb70c8b5d4d102e4572e4e5bcffc8 |
| O_AFTER_SECRET_INSPECT | O_AFTER_VOLUME_INSPECT | 0 | 1 | 1000 | bf0e5a25a8efa2585f3399372eab5a5b57161de423f6eeab626e2cde0499c298 |
| O_AFTER_CONTAINER_INSPECT | O_AFTER_SECRET_INSPECT | 0 | 1 | 1000 | ceeadbf54727da6f98abb5f3885e4d47ad5f41f45747eb42425cead340978e02 |
| IMAGE_INITDB_CHILD_1 | IMAGE_INITDB | 0 | 1 | 300 | e6d0d31d7ecaaf4f6409d829b8e4865446f1791361855c86c9e758d7bcbd5069 |
| IMAGE_INITDB_CHILD_2 | IMAGE_INITDB | 0 | 1 | 300 | ebfd4ec80e129410b8be692b02c3fbcee242e99347dc9426b8bb82691f31e7c4 |
| IMAGE_INITDB_CHILD_3 | IMAGE_INITDB | 0 | 1 | 300 | 2431b84662226c9c6e5e323e9405694e342a0c39aea150b40c04e512c8c58717 |
| IMAGE_INITDB_CHILD_4 | IMAGE_INITDB | 0 | 1 | 300 | 3a1ac2b161c838b52b2ba531182cb3a83fb6033af6e6c15fdca915166aae02a5 |
| IMAGE_INITDB_CHILD_5 | IMAGE_INITDB | 0 | 1 | 300 | 65339c91c11b7f19949d1fe445138771ec7a0db685eabb92a265261486411e7d |
| OWNER_FIXTURE_AUTH_CONNECT | OWNER_AUTH_CONNECT | 0 | 1 | 300 | e3a0f1695a14afe7f8aa85b6d744fa6c6fdd28213699484dd004c2b3cd6fe502 |

```sql
-- CREATE_DATABASE
CREATE DATABASE {database} OWNER postgres;

-- REVOKE_DATABASE
REVOKE ALL ON DATABASE {database} FROM PUBLIC;

-- REVOKE_SCHEMA
REVOKE ALL ON SCHEMA public FROM PUBLIC;

-- CREATE_PROBE_ROLE
CREATE ROLE {probe_role} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 1;

-- SET_SCRAM_VERIFIER
ALTER ROLE {probe_role} PASSWORD {scram_verifier_literal};

-- REVOKE_DEFAULT_FUNCTION
ALTER DEFAULT PRIVILEGES REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;

-- CONNECT_ONLY
GRANT CONNECT ON DATABASE {database} TO {probe_role};

-- READ_ONLY_DEFAULT
ALTER ROLE {probe_role} SET default_transaction_read_only=on;

-- TIMEOUT_DEFAULT
ALTER ROLE {probe_role} SET statement_timeout='100ms';

-- RAW_OWNER_ROLE_AUDIT
SELECT current_database(),current_user,current_setting('server_version_num'),system_identifier,p.rolsuper,p.rolcreatedb,p.rolcreaterole,p.rolinherit,p.rolreplication,p.rolbypassrls,p.rolconnlimit,ARRAY(SELECT roleid FROM pg_auth_members WHERE member=p.oid),has_database_privilege(p.oid,current_database(),'CREATE'),has_database_privilege(p.oid,current_database(),'TEMP'),has_schema_privilege(p.oid,'public','CREATE') FROM pg_control_system(),pg_roles p WHERE p.rolname=%s;

-- AUTH_CONFIG_AUDIT
SELECT rule_number,auth_method,error FROM pg_hba_file_rules ORDER BY rule_number;

-- USER_OBJECT_PRIVILEGE_AUDIT
SELECT c.oid,has_table_privilege(%s,c.oid,'SELECT'),has_table_privilege(%s,c.oid,'INSERT,UPDATE,DELETE,TRUNCATE,MAINTAIN') FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' ORDER BY c.oid;
```

Totals: **12 SQL / 32 command reservations / 29,000 ms allocated**.
This is not proof that a cold start fits 30 seconds. No P50/P95 result exists.
The prior 26 OS/auth operations are retained. Five initdb descendant command slots
are conservative placeholders, not a measured bound; one additional Owner fixture
authentication slot accounts for CREATE DATABASE's separate connection. Native
mkdir/write/fsync/rename/ownership checks are declared filesystem operations, not
free hidden shell executions. initdb's internal backend/bootstrap work is NOT
a claim of zero SQL: exact descendant/internal work remains to be censused and
classified before D1 can be certified. The current abstract DAG does not itself
enforce inter-process scheduling or reserve every native child.

No automatic health loop. One explicit readiness call is budgeted and does not
replace actual SCRAM login. Owner has bootstrap, fixture and probe authentication.
D3 additionally declares two independent Owner session-identity SQL audits, each
100ms, with connection costs separately unresolved. They are NOT a seventeenth
probe query and NOT silently charged to zero or the eight warmups.

## Strategy Comparison

FRESH_DYNAMIC creates one database/role after a committed attempt. It cannot run
under active limits. SINGLE_USE_PREBUILT is a costed planning alternative only:
all builder costs remain in the aggregate ledger (not free runtime work); actual
single-use allocation, artifact attestation and consumed-once builder are still
unimplemented. Neither strategy is approved or measured.

PersistentBootstrapBudget shares B's append-only named slots and records boot,
monotonic/wall origin and plan hash. Duplicate reservations, restarted start,
unknown name and exceeded deadline fail. A complete trusted manager/native helper
reservation bridge is still a SOURCE gap. A local CandidateBudget is a model
counter, not evidence of global enforcement. Do not approve this ledger merely
because its declared sum is below 30s.
