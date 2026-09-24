import React, { useEffect, useState } from "react";
import ControlGroup from "@splunk/react-ui/ControlGroup";
import Select from "@splunk/react-ui/Select";
import { EDITOR_THEME_CHOICES } from "../themes/presets";
import { loadThemePreset, persistThemePreset } from "../themes/settings";

export default function EditorThemeSelect({ label = "Theme", minWidth = 168 }) {
    const [preset, setPreset] = useState("tokyo_night");
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");

    useEffect(() => {
        loadThemePreset().then(setPreset).catch(() => {});
    }, []);

    const onChange = (e, { value }) => {
        if (!value || value === preset) {
            return;
        }
        setBusy(true);
        setError("");
        persistThemePreset(value)
            .then((saved) => setPreset(saved))
            .catch((err) => {
                setError(err && err.message ? err.message : "Could not save theme");
            })
            .finally(() => setBusy(false));
    };

    return (
        <ControlGroup
            label={label}
            labelPosition="top"
            error={error || undefined}
            help={error ? undefined : "Applies to all SplunkUI pages for this deployment."}
        >
            <div style={{ minWidth }}>
                <Select
                    value={preset}
                    onChange={onChange}
                    disabled={busy}
                    aria-label="Editor color theme"
                >
                    {EDITOR_THEME_CHOICES.map((choice) => (
                        <Select.Option
                            key={choice.value}
                            label={choice.label}
                            value={choice.value}
                        />
                    ))}
                </Select>
            </div>
        </ControlGroup>
    );
}
