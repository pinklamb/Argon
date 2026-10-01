function classify(value) {
  if (value > 0 && value < 10) return "small";
  switch (value) {
    case 1:
      return "one";
    case 2:
      return "two";
    default:
      return value ? "other" : "zero";
  }
}
