# I Built a Cloud-Native Fraud Detection Platform, Then Rebuilt the Path to the Product When the Cloud Failed Me

*How SentinelStream grew from a systems design challenge into a working analyst platform, a local desktop app, and one of the most important engineering milestones in my journey so far.*

## Why I Built SentinelStream

Some projects start because you want to learn a new framework. SentinelStream started because I wanted to build something that forced me to think like a systems engineer, a platform builder, and a product owner at the same time.

Fraud detection sits at an interesting intersection. It is part security problem, part data problem, part operations problem, and part decision-making problem. It is not enough to simply classify events as “good” or “bad.” A usable system needs to ingest activity, enrich it, score it, apply business logic, produce an explainable decision, and leave a clear path for a human analyst to review what happened and why.

That challenge was exactly what made SentinelStream worth building.

I did not want to build a toy notebook and call it a platform. I wanted something closer to a real operational system: event-driven, observable, deployable, and modular enough to grow into a serious product. I wanted to prove I could build more than isolated services. I wanted to build the entire path from ingestion to analyst review.

## What SentinelStream Actually Is

At a high level, SentinelStream is a cloud-native fraud detection and analyst decision-support platform. It is designed to take suspicious financial or transactional activity, process it through multiple services, combine rules with machine learning, and present the output to an analyst through a review console.

The platform is built as Python microservices, with FastAPI powering the service layer. The core services are:

- `ingestion-service`
- `feature-service`
- `rule-engine`
- `model-service`
- `decision-service`
- `feedback-service`
- `analyst-console`

The data path is intentionally modular.

The `ingestion-service` accepts events and publishes them into the event pipeline. The `feature-service` derives context and lookup features. The `rule-engine` applies deterministic fraud rules. The `model-service` contributes model inference and scoring. The `decision-service` brings those dependencies together, produces the final decision, and exposes the API that the analyst side consumes. The `feedback-service` closes the loop by allowing analyst review and label capture. Finally, the `analyst-console` gives the human operator a usable surface for inspecting decisions and sending feedback back into the system.

Supporting that flow are Postgres for persistence, Redis for caching, and Kafka-compatible messaging through Redpanda for event-driven communication. Observability was also treated as a first-class part of the architecture: structured logs, tracing, metrics, and OpenTelemetry were all part of the platform design instead of something bolted on later.

## Why the Architecture Matters

One of the biggest decisions in this build was not technical syntax. It was architectural intent.

I chose a microservices approach because fraud systems benefit from separation of concerns. Feature computation, scoring, rules, feedback, and analyst workflows do not change at the same pace. Keeping them modular makes experimentation, debugging, and future scaling easier. It also forces clearer service contracts.

I chose an event-driven design because risk systems often need to react to streams of activity, not just isolated request-response calls. Events make it easier to decouple producers from downstream processors and introduce more realistic operational behavior into the system.

I also deliberately avoided a false choice between rules and machine learning. In real fraud and cybersecurity workflows, rules still matter. Rules are fast, explicit, and easy to explain. Machine learning can capture more complex patterns, but it benefits from guardrails, observability, and human oversight. SentinelStream was designed around the idea that a practical detection system can use both.

And that last point matters just as much: human oversight. I did not want the project to stop at backend scoring. The analyst workflow is part of the product. If the platform cannot surface decisions in a way a human can inspect and act on, then it is incomplete.

## The Hard Engineering Reality

This project did not move from architecture diagram to deployment in a straight line.

That is one reason this milestone matters to me.

The infrastructure path included Terraform, ECR, EKS, Helm, GitHub Actions, Kubernetes manifests, and deployment workflows. That meant the problems were not only “does this code compile?” but also “does the environment behave the way the system assumes it will?”

Some of the work looked deceptively small but mattered a lot:

- fixing Terraform multi-repository ECR outputs
- fixing ECR lifecycle behavior for tagged images
- adjusting the dev EKS node type to fit a more realistic cost path
- adding a demo-data Kubernetes stack for Postgres, Redis, and Redpanda
- fixing the model bootstrap workflow to run correctly as a module
- fixing Helm annotation typing after Kubernetes rejected numeric annotation values
- changing the analyst console service exposure from `LoadBalancer` to `ClusterIP` for a more practical dev shape
- adding much better deployment diagnostics when things failed

Then came the deeper debugging.

Services were crash-looping. Startup timing became a real issue. Some failures were direct dependency issues, while others were just noisy side effects of earlier startup failures. I had to trace Postgres connection settings all the way from configuration through async SQLAlchemy and `asyncpg` to prove what hostname was actually being used at runtime. I had to separate primary failures from secondary warnings, including Kafka producer and consumer cleanup warnings that appeared only because the app crashed before graceful shutdown.

That work pushed the project from “services exist” into “services behave like a platform.”

I ended up hardening startup order, readiness assumptions, and cleanup behavior in ways that mattered across the whole stack. This is where distributed systems teach humility quickly: elegant code means very little if startup, health, cleanup, and dependency sequencing are fragile.

## When the Cloud Path Broke

The biggest disruption was not a syntax error. It was infrastructure reality.

The AWS deployment path was real. The repo had Terraform, EKS design, Helm deployment, CI/CD, and container builds. But at a critical point, the AWS account became suspended. That meant the cloud path, even though it had been engineered seriously, stopped being the reliable route for demonstrating the platform.

That moment could have reduced the project to a dead-end deployment story.

Instead, it forced a much better lesson: if the product outcome matters, then the delivery path needs resilience too.

I stopped treating AWS as the only valid finish line. That changed the way I thought about the project.

## The Pivot That Saved SentinelStream

The most important product decision in this milestone was the pivot to a local fallback deployment path.

Rather than abandon the cloud-native design, I adapted it for local operation while preserving the architectural intent. The goal was not to throw everything into a quick disposable demo. The goal was to make the same system shape more reproducible and more portable.

That led to a local Kubernetes flow built around the existing Helm chart and demo-data manifests. I stabilized the dependency layer for Postgres, Redis, and Redpanda. I added more reliable startup handling. I made local image build and load workflows straightforward. I reduced the gap between “system designed for cloud” and “system I can actually show, test, and iterate on today.”

This was not just a deployment workaround. It was an architectural maturity moment.

A platform that only works when every ideal cloud assumption holds is less resilient than it looks on paper. SentinelStream became stronger because it learned how to survive outside that narrow path.

## The Desktop App Milestone

Once the local platform path became workable, the next question changed from “can this run?” to “can this feel like a product?”

That is where the analyst desktop milestone came in.

I packaged the analyst console into a Windows desktop shell using Electron. This was an important shift. Before that, SentinelStream could be described as an impressive backend platform. After that, it started looking more like a usable product artifact.

The desktop work introduced several product-facing improvements:

- a dedicated Windows installer build
- a portable executable build
- embedded and external launch modes
- persisted desktop settings
- startup and fallback screens
- Store-preparation documentation for future Microsoft Store release work

That step also surfaced a different class of engineering problems. Packaging is not the same as coding. I had to deal with output collisions between build targets, embedded-mode path assumptions that broke in packaged builds, and the difference between a developer-run shell and a user-facing desktop experience.

Those problems were worth solving because they moved the project from infrastructure-centric credibility into product-centric credibility.

## What I Learned

SentinelStream taught me several lessons that I will carry into every serious system I build next.

First, architecture is only impressive if it survives contact with operations. A diagram that looks clean but cannot tolerate dependency timing, deployment variance, or infrastructure failure is incomplete.

Second, observability is not optional. Logs, health checks, traces, and diagnostics are what turn “it failed” into “I know why it failed.” In distributed systems, that difference is everything.

Third, graceful startup and shutdown matter more than they seem. Some of the ugliest failure signals in this project were not the original errors themselves, but the noise created when failed startup prevented proper cleanup. Fixing resource cleanup and lifecycle handling improved clarity as much as correctness.

Fourth, fallback paths are part of product design. The move from AWS-only thinking to local Kubernetes and then to a desktop shell was one of the most valuable design decisions in the whole project. It preserved the user outcome even when the initial infrastructure plan was blocked.

And finally, there is a real difference between building code and building something people can actually use. The analyst console, the desktop shell, the installer outputs, and the Store-readiness planning all pushed SentinelStream closer to the latter.

## Why This Milestone Matters to Me

There are projects you finish and move on from quickly.

Then there are projects that mark a turning point in how you think.

SentinelStream is one of those for me.

It forced me to work across architecture, backend services, event-driven design, infrastructure as code, Kubernetes deployment, CI/CD, debugging, product packaging, and public-release thinking. It asked more than “can you build this service?” It kept asking, “can you make this system believable, resilient, and usable?”

That is why this milestone matters so much.

It is not just that I built a fraud detection platform. It is that I learned how to keep moving when the clean path broke. I learned how to pivot without discarding the original vision. I learned how to treat deployment, product surface, and user outcome as part of the engineering work rather than afterthoughts.

Today, SentinelStream exists not just as a set of services, but as a platform with a story, a fallback path, a desktop artifact, and a clearer route toward productization.

And that, to me, is worth archiving.

## Key Takeaways

- Serious systems become real when architecture, operations, and usability meet.
- Rules, machine learning, and analyst oversight are stronger together than in isolation.
- Cloud-native design should include local or fallback deployment thinking.
- Debugging startup order and lifecycle cleanup is a core distributed-systems skill.
- Productization starts when the system becomes usable, not just deployable.

## LinkedIn Teaser

I just archived one of the most meaningful engineering milestones in my journey so far: building SentinelStream, a cloud-native, event-driven fraud detection and analyst decision-support platform, then pivoting it into a working local and desktop-ready product path when the original cloud route was blocked. It pushed me across microservices, Kubernetes, Terraform, CI/CD, observability, debugging, and Windows desktop packaging — and taught me more about resilient product engineering than any “smooth” build ever could.

## Suggested Tags

- Software Engineering
- Cybersecurity
- Fraud Detection
- Microservices
- Kubernetes
- DevOps
- Python
- Product Engineering

## Editor's Note

Best places to add visuals before publishing:

1. Architecture diagram after the “What SentinelStream Actually Is” section
2. Kubernetes or service health screenshot in “The Hard Engineering Reality”
3. Analyst console screenshot in “The Desktop App Milestone”
4. Desktop installer or packaged app screenshot near the conclusion
