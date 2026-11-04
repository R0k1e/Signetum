# Concurrent and background work

Use these rules when introducing or changing concurrent, background or lazy
paths. They generalize observed development failures; they do not prescribe an
application framework or a permanent worker ceiling.

Give initialization one owner at the resource's actual scope. Competing callers
join its in-flight result; define failure and retry explicitly. Publish only
complete state. Trace foreground use of any resource prepared in the background,
including cancellation and shutdown before preparation completes.

Establish order with events, acknowledged readiness or deterministic handshakes,
not sleeps. Start a deadline at the operation it bounds; queueing and admission
need their own bounds. Own ports, child handles, scratch and reports at acquisition;
retain stable identity through release. Stop admission before settling accepted
work, then release dependencies after owned children stop.

Extend existing public-boundary tests with deterministic overlap at the contested
boundary. Cover failure and cancellation where the new path can race. Use the
existing allocator for a bounded contention run with explicit width and synthetic
CPU pressure when this addresses the failure class. Record actual allocation,
pressure setup, targets and outcome in ordinary evidence; this creates no global
load gate or timing budget. A serial pass does not prove contention correctness.
Root-cause first failures; a solo diagnostic retry never discharges the defect.
