import aicteLogo from '../assets/aicte-emblem.png'

export function Mark({ size = 44 }) {
  return (
    <img src={aicteLogo} width={size} height={size} alt="AICTE — All India Council for Technical Education" className="mark" style={{ flexShrink: 0, objectFit: 'contain' }} />
  )
}
