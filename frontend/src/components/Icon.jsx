/* Feather icons (the icon set the Duralux template uses), via react-icons. */
import {
  FiActivity, FiAirplay, FiAlertTriangle, FiBell, FiCalendar, FiCheck, FiCheckCircle, FiChevronDown, FiChevronRight,
  FiClock, FiDownload, FiFileText, FiFilter, FiGrid, FiHome, FiInbox, FiLink2, FiLogOut, FiMail, FiMenu, FiMoreVertical,
  FiPlus, FiRefreshCw, FiSearch, FiShield, FiSliders, FiTrendingUp, FiUpload, FiUsers, FiX, FiLayers, FiBarChart2,
  FiAlignLeft, FiPrinter, FiEdit3, FiEye, FiInfo, FiPause, FiCircle,
} from 'react-icons/fi'

const MAP = {
  dashboard: FiAirplay, file: FiFileText, calendar: FiCalendar, shield: FiShield, clock: FiClock, bell: FiBell,
  download: FiDownload, chain: FiLink2, sliders: FiSliders, home: FiHome, menu: FiAlignLeft, hamburger: FiMenu,
  search: FiSearch, inbox: FiInbox, check: FiCheck, checkCircle: FiCheckCircle, alert: FiAlertTriangle, users: FiUsers,
  logout: FiLogOut, chevron: FiChevronRight, chevronDown: FiChevronDown, more: FiMoreVertical, trend: FiTrendingUp,
  activity: FiActivity, filter: FiFilter, grid: FiGrid, mail: FiMail, plus: FiPlus, refresh: FiRefreshCw,
  upload: FiUpload, x: FiX, layers: FiLayers, chart: FiBarChart2, printer: FiPrinter, edit: FiEdit3, eye: FiEye,
  close: FiX, info: FiInfo, pause: FiPause, circle: FiCircle,
}

export default function Icon({ name, size = 18, className = '', strokeWidth }) {
  const C = MAP[name] || FiFileText
  return <C size={size} className={`icon ${className}`} aria-hidden="true" {...(strokeWidth ? { strokeWidth } : {})} />
}
