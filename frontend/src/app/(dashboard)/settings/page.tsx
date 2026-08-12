import { Settings } from 'lucide-react';

export default function SettingsPage() {
  return (
    <div className="empty-state">
      <div className="empty-state-icon"><Settings size={32} strokeWidth={1.5} /></div>
      <h2 className="empty-state-title">Settings</h2>
      <p className="empty-state-description">
        Manage your organization, team members, detection thresholds, notification preferences,
        and API keys. Coming soon.
      </p>
    </div>
  );
}
