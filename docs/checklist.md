# Architecture Review Checklist

Use alongside the automated scan. Mark each item ✅ OK, ⚠️ Needs attention, ❌ Risk, or N/A.

## 1. Business context
- [ ] Main business goals and pain points are written down
- [ ] Critical user journeys and their expected load are known
- [ ] Non-functional requirements are defined (availability, response time, data retention)
- [ ] Constraints are clear (budget, team size, compliance, deadlines)

## 2. Architecture & design
- [ ] An up-to-date architecture diagram exists (C4 context + container level)
- [ ] Module / service boundaries follow business capabilities
- [ ] Dependencies point in one direction; no circular references
- [ ] Business rules live in the domain/application layer, not in controllers or SQL
- [ ] Synchronous vs. asynchronous communication is a deliberate choice
- [ ] The monolith vs. microservices choice fits team size and scale
- [ ] Key decisions are recorded (Architecture Decision Records)

## 3. Code quality
- [ ] Consistent structure and naming across projects
- [ ] No "god classes" or very large files in core paths
- [ ] Error handling is consistent (problem details, no swallowed exceptions)
- [ ] Logging is structured and includes correlation IDs
- [ ] Static analysis / analyzers are enabled in the build
- [ ] Technical-debt markers (TODO/FIXME) are tracked in the backlog

## 4. Data
- [ ] Database schema is versioned (EF migrations or equivalent)
- [ ] Indexes support the main queries; slow queries are known
- [ ] Transactions and concurrency are handled explicitly
- [ ] Backups are automated **and restores are tested**
- [ ] Personal data is identified, minimised and protected

## 5. Security
- [ ] No secrets in source control (Key Vault / user secrets / environment variables)
- [ ] Authentication and authorisation are centralised and tested
- [ ] Input validation on all external inputs
- [ ] Dependencies are scanned for vulnerabilities
- [ ] HTTPS everywhere; security headers configured
- [ ] Least-privilege access for services and databases

## 6. Performance & scalability
- [ ] Load expectations are known and tested
- [ ] Caching strategy is defined where it matters
- [ ] Long-running work is moved to background processing
- [ ] External calls have timeouts, retries and circuit breakers
- [ ] The app can scale horizontally (stateless, no local file state)

## 7. DevOps & operations
- [ ] CI builds and tests on every pull request
- [ ] Deployments are automated and repeatable (CD, infrastructure as code)
- [ ] Separate environments (dev / test / prod) with config per environment
- [ ] Monitoring, alerts and dashboards exist for key metrics
- [ ] Health checks are exposed and used by the platform
- [ ] Rollback procedure is documented

## 8. Testing
- [ ] Unit tests cover business rules
- [ ] Integration tests cover data access and external integrations
- [ ] Critical user journeys have end-to-end or API tests
- [ ] Tests run quickly and reliably in CI

## 9. Team & process
- [ ] Code review is required before merge
- [ ] Onboarding documentation lets a new developer run the system in a day
- [ ] Ownership of each component is clear
- [ ] AI-assisted development tools are used with review guidelines
