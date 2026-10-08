### Why does each pretend user have its own seeded random generator?

1. Each pretend user has its own random number generator so that one user's random actions do not directly affect another user's random sequence.
2. Using a seed allows us to reproduce the same simulated behaviour when we run an experiment again with the same setup.
3. This makes our experiments easier to test, compare, and debug because we can identify whether a change in the results comes from our code or from different random outcomes.
