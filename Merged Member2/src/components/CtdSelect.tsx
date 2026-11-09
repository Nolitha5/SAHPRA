import { CTD_GROUPS } from '../ctd'

// Indentation inside <option> must use non-breaking spaces (normal spaces are collapsed).
const INDENT = ['', '   ', '      ']

/** A CTD section dropdown grouped by part (Module 3 / 3.2.S / 3.2.P), with official heading names. */
export default function CtdSelect({ id, value, onChange, emptyLabel }: {
  id: string
  value: string
  onChange: (value: string) => void
  emptyLabel?: string // e.g. "Any section"; omit to force a choice
}) {
  return (
    <select id={id} value={value} onChange={e => onChange(e.target.value)}>
      {emptyLabel !== undefined && <option value="">{emptyLabel}</option>}
      {CTD_GROUPS.map(group => (
        <optgroup key={group.label} label={group.label}>
          {group.headings.map(h => (
            <option key={h.code} value={h.code}>{`${INDENT[h.level]}${h.code}  ${h.title}`}</option>
          ))}
        </optgroup>
      ))}
    </select>
  )
}
