function grade(score, bonus) {
  if (score > 90 && bonus) {
    return "A";
  } else if (score > 75) {
    return "B";
  }
  for (const s of [1, 2]) {}
  return score > 50 ? "C" : "F";
}
