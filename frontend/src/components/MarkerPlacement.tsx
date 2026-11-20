'use client';

import { useState } from 'react';

export type MarkerPlacementValues = {
  physical_size_m: string; description: string;
  world_x: string; world_y: string; world_z: string;
  normal_x: string; normal_y: string; normal_z: string; rotation_deg: string;
};
export type BIMElementOption = { guid: string; label: string; expressID: number };

export default function MarkerPlacement({ values, onChange, elements, selectedGuid, onSelect,
  onSave, onCancel, saving }: {
  values: MarkerPlacementValues;
  onChange: (value: MarkerPlacementValues) => void;
  elements: BIMElementOption[];
  selectedGuid: string | null;
  onSelect: (guid: string) => void;
  onSave: (dictionary: string) => Promise<void>;
  onCancel: () => void;
  saving: boolean;
}) {
  const [search, setSearch] = useState('');
  const [dictionary, setDictionary] = useState('DICT_4X4_50');
  const [offset, setOffset] = useState({ x: '0', y: '0', z: '0' });
  const [message, setMessage] = useState('');
  const update = (key: keyof MarkerPlacementValues, value: string) => onChange({ ...values, [key]: value });
  return <form onSubmit={async e => { e.preventDefault(); await onSave(dictionary); }} style={{ display: 'grid', gap: 12, padding: 12 }}>
    <p>Select an element, then click its face where the centre of the printed marker will be installed. One visible registered marker can calibrate a fixed camera.</p>
    <label>Find a BIM element
      <input className="input" placeholder="Column name, type or GUID" value={search} onChange={e => setSearch(e.target.value)} />
    </label>
    <label>Element
      <select className="input" value={selectedGuid || ''} onChange={e => onSelect(e.target.value)} required>
        <option value="">Select an element</option>
        {elements.filter(element => element.guid === selectedGuid || element.label.toLowerCase().includes(search.toLowerCase()))
          .map(element => <option key={element.guid} value={element.guid}>{element.label}</option>)}
      </select>
    </label>
    <p>{values.world_x ? `Marker centre in BIM metres: X ${Number(values.world_x).toFixed(3)}, Y ${Number(values.world_y).toFixed(3)}, Z ${Number(values.world_z).toFixed(3)}` : 'Click the selected surface in the 3D view to set the marker centre.'}</p>
    <label>Printed black square side (metres)
      <input className="input" required type="number" min="0.01" max="2" step="0.001" value={values.physical_size_m} onChange={e => update('physical_size_m', e.target.value)} />
    </label>
    <label>Pattern family
      <select className="input" value={dictionary} onChange={e => setDictionary(e.target.value)}>
        <option value="DICT_4X4_50">4 × 4 — up to 50 locations</option>
        <option value="DICT_6X6_250">6 × 6 — up to 250 locations</option>
      </select>
    </label>
    <p>An unused pattern ID is assigned when you save. Download its print from the marker card, print at 100% scale, and measure the black square before installation.</p>
    <label>Printed orientation (degrees around the surface normal)
      <input className="input" type="number" min="-360" max="360" step="1" required value={values.rotation_deg} onChange={e => update('rotation_deg', e.target.value)} />
    </label>
    <button type="button" className="btn btn-secondary" onClick={() => onChange({ ...values,
      normal_x: String(-Number(values.normal_x)), normal_y: String(-Number(values.normal_y)), normal_z: String(-Number(values.normal_z)) })}>Flip marker-facing direction</button>
    <p>The square preview shows the marker face. The arrow points out towards the camera; the coloured top edge identifies the top of the print.</p>
    <label>Installation note (optional)
      <input className="input" placeholder="Column C1, east face" value={values.description} onChange={e => update('description', e.target.value)} />
    </label>
    <details><summary>Measured offsets and BIM coordinates</summary>
      <p>To use a corner as a reference, click that corner, then apply the measured offset to the marker centre in BIM axes. Z is elevation. Verify these measurements on site.</p>
      {(['x', 'y', 'z'] as const).map(axis => <label key={axis}>Offset {axis.toUpperCase()} (metres)
        <input className="input" type="number" step="any" value={offset[axis]} onChange={e => setOffset({ ...offset, [axis]: e.target.value })} />
      </label>)}
      <button type="button" className="btn btn-secondary" onClick={() => {
        if (!values.world_x || !Object.values(offset).every(v => v.trim() && Number.isFinite(Number(v)))) { setMessage('Choose a reference point and enter numeric offsets.'); return; }
        onChange({ ...values, world_x: String(Number(values.world_x) + Number(offset.x)),
          world_y: String(Number(values.world_y) + Number(offset.y)), world_z: String(Number(values.world_z) + Number(offset.z)) });
        setOffset({ x: '0', y: '0', z: '0' }); setMessage('Offsets applied to the marker centre.');
      }}>Apply offsets</button>
      <p role="status">{message}</p>
      {(['world_x', 'world_y', 'world_z', 'normal_x', 'normal_y', 'normal_z'] as const).map(key => <label key={key}>{key.replaceAll('_', ' ')}
        <input className="input" type="number" step="any" value={values[key]} onChange={e => update(key, e.target.value)} />
      </label>)}
    </details>
    <button className="btn btn-primary" disabled={saving || !values.world_x || !selectedGuid}>{saving ? 'Saving marker…' : 'Save and assign marker ID'}</button>
    <button className="btn btn-secondary" type="button" onClick={onCancel} disabled={saving}>Cancel</button>
  </form>;
}
