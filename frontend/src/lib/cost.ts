export function formatCost(dollars: number): string {
  if (dollars === 0) return '$0.0000'
  return `$${dollars.toFixed(4)}`
}
