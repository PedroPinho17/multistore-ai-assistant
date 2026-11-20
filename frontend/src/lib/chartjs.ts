/**
 * The only module that imports Chart.js. Named imports (never `import('chart.js')` as a
 * namespace) let the build drop the controllers and plugins nobody uses (pie, radar,
 * scatter, …).
 *
 * Always load it lazily: chart.ts (chat) is itself loaded with import(), and
 * dash-charts.ts / admin-charts.ts load this file with import(). It must never be
 * imported statically from code that is in the start-up bundle.
 */
import {
  BarController,
  BarElement,
  CategoryScale,
  Chart,
  Filler,
  Legend,
  LinearScale,
  LineController,
  LineElement,
  PointElement,
  Tooltip,
} from 'chart.js'

// Everything the chat, the dashboard and the admin page draw (bar and line charts).
// Legend: only the admin "requests per day" chart shows it; the others turn it off.
Chart.register(
  BarController,
  LineController,
  BarElement,
  LineElement,
  PointElement,
  CategoryScale,
  LinearScale,
  Filler,
  Tooltip,
  Legend,
)

export { Chart }
