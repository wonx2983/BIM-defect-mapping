'use client';
import { useEffect, useState } from 'react';
import { getDetectionConfig, type DetectionConfig } from '@/lib/api/detection';
import { useAuthStore } from '@/stores/authStore';

export default function SettingsPage() {
  const user = useAuthStore(s => s.user);
  const [config, setConfig] = useState<DetectionConfig | null>(null);
  const [error, setError] = useState('');
  useEffect(() => { getDetectionConfig().then(setConfig).catch(e => setError(String(e))); }, []);
  return <div style={{ padding: 24 }}>
    <h1>Account and detection settings</h1>
    <p>{user?.full_name} · {user?.email} · {user?.role}</p>
    {error && <p role="alert">{error}</p>}
    {config && <dl>
      <dt>Detector</dt><dd>{config.model_name}</dd>
      <dt>Confidence threshold</dt><dd>{config.confidence_threshold}</dd>
      <dt>Processing device</dt><dd>{config.device}</dd>
      <dt>Classes</dt><dd>{config.supported_classes.join(', ')}</dd>
    </dl>}
    <p>Detector thresholds are managed by the deployment administrator so evaluations use a consistent configuration.</p>
    <p>Severity is an automated estimate. Confirm findings with a qualified reviewer before making inspection decisions.</p>
  </div>;
}
