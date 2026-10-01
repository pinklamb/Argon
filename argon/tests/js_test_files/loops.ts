export function total(values: number[]) {
  let sum = 0;
  for (const value of values) {
    if (value > 0) sum += value;
  }
  while (sum < 10) sum++;
  return sum;
}
