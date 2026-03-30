import { useState } from 'react';
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
  const [expanded, setExpanded] = useState(false);

  return (
    <>
      {/* Desktop: always visible */}
      <div className="hidden md:block absolute bottom-12 left-3 bg-white/90 backdrop-blur-sm rounded-lg shadow-md px-3 py-2 z-10 text-xs">
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

      {/* Mobile: collapsible icon button */}
      <div className="md:hidden absolute bottom-3 left-3 z-10">
        {expanded ? (
          <div className="bg-white/95 backdrop-blur-sm rounded-lg shadow-md px-3 py-2 text-xs">
            <div className="flex items-center justify-between mb-1">
              <span className="font-semibold text-gray-700">{palette.label}</span>
              <button
                onClick={() => setExpanded(false)}
                className="text-gray-400 hover:text-gray-600 ml-2 p-0.5"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div className="grid grid-cols-2 gap-x-3 gap-y-0.5">
              {Object.entries(palette.entries).map(([label, color]) => (
                <div key={label} className="flex items-center gap-1">
                  <span
                    className="w-2 h-2 rounded-full inline-block flex-shrink-0"
                    style={{ backgroundColor: `rgb(${color[0]},${color[1]},${color[2]})` }}
                  />
                  <span className="text-gray-600 text-[10px]">{label}</span>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <button
            onClick={() => setExpanded(true)}
            className="bg-white/90 backdrop-blur-sm rounded-lg shadow-md p-2 text-gray-600 hover:text-gray-800"
            title="Show legend"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M11.25 11.25l.041-.02a.75.75 0 011.063.852l-.708 2.836a.75.75 0 001.063.853l.041-.021M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-9-3.75h.008v.008H12V8.25z" />
            </svg>
          </button>
        )}
      </div>
    </>
  );
}
