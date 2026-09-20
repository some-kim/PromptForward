import type { Challenge, Problem } from "./api";

export function toChallenge(problem: Problem): Challenge {
  return {
    id: problem.id,
    type: "image",
    difficulty: problem.difficulty,
    imageUrl: problem.imageUrl,
    problem: {
      slug: problem.slug,
      title: problem.title,
      skill: problem.skill,
      skillTitle: problem.skillTitle,
      order: problem.order,
    },
  };
}

// The next unsolved problem in curriculum order, or the first one if all are solved.
export function nextProblem(
  problems: Problem[],
  afterId?: string,
): Problem | undefined {
  const start = afterId
    ? problems.findIndex((problem) => problem.id === afterId) + 1
    : 0;
  const rotated = [...problems.slice(start), ...problems.slice(0, start)];
  return (
    rotated.find((problem) => problem.status !== "solved") ??
    rotated.find((problem) => problem.id !== afterId) ??
    rotated[0]
  );
}
