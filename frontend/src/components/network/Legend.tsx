import type { ColorByMode } from '../../types/network';
import { CENTURY_COLORS, ROLE_COLORS, OCCUPATION_COLORS } from '../../types/network';

interface Props {
  colorBy: ColorByMode;
}

const PALETTES: Record<ColorByMode, { label: string; entries: Record<string, [number, number, number]> }> = {
  century: { label: 'Life Period', entries: CENTURY_COLORS },
  role: { label: 'Role', entries: ROLE_COLORS },
  occupation: { label: 'Occupation', entries: OCCUPATION_COLORS },
};

export default function Legend({ colorBy }: Props) {
  const palette = PALETTES[colorBy];

  return (
    <div className="absolute bottom-12 left-3 bg-white/90 backdrop-blur-sm rounded-lg shadow-md px-3 py-2 z-10 text-xs">
      <div className="font-semibold text-gray-700 mb-1">{palette.label}</div>
      <div className="grid grid-cols-2 gap-x-4 gap-y-0.5">
        {Object.entries(palette.entries).map(([label, color]) => (
          <div key={label} className="flex items-center gap-1.5">
            <span
              className="w-2.5 h-2.5 rounded-full inline-block flex-shrink-0"
              style={{ backgroundColor: `rgb(${color[0]},${color[1]},${color[2]})` }}
            />
            <span className="text-gray-600">{label}</span>
          </div>
        ))}
      </div>
      <div className="mt-1 text-gray-400 border-t pt-1">Size = connections</div>
    </div>
  );
}
