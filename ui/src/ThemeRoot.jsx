import React, { useCallback, useEffect, useState } from "react";
import { SplunkThemeProvider } from "@splunk/themes";
import { applyAppTheme, resolveAppTheme } from "./theme";
import { STIG_THEME_UPDATED } from "./themes/themeEvents";

export default function ThemeRoot({ children }) {
    const [theme, setTheme] = useState(null);

    const reloadTheme = useCallback(() => {
        return resolveAppTheme()
            .then((next) => {
                applyAppTheme(next);
                setTheme(next);
                return next;
            })
            .catch(() => {
                const fallback = {
                    family: "prisma",
                    colorScheme: "dark",
                    density: "comfortable",
                    presetId: "tokyo_night",
                    palette: null,
                };
                applyAppTheme(fallback);
                setTheme(fallback);
            });
    }, []);

    useEffect(() => {
        reloadTheme();
    }, [reloadTheme]);

    useEffect(() => {
        const onRefresh = (event) => {
            const detail = event && event.detail;
            if (detail && detail.palette) {
                applyAppTheme(detail);
                setTheme(detail);
                return;
            }
            reloadTheme();
        };
        const onVisibility = () => {
            if (!document.hidden) {
                reloadTheme();
            }
        };
        window.addEventListener(STIG_THEME_UPDATED, onRefresh);
        window.addEventListener("focus", onRefresh);
        document.addEventListener("visibilitychange", onVisibility);
        return () => {
            window.removeEventListener(STIG_THEME_UPDATED, onRefresh);
            window.removeEventListener("focus", onRefresh);
            document.removeEventListener("visibilitychange", onVisibility);
        };
    }, [reloadTheme]);

    if (!theme) {
        return null;
    }

    const colorScheme = theme.colorScheme === "light" ? "light" : "dark";
    return (
        <SplunkThemeProvider
            key={theme.presetId || theme.palette?.id || colorScheme}
            family={theme.family || "prisma"}
            colorScheme={colorScheme}
            density={theme.density || "comfortable"}
        >
            {children}
        </SplunkThemeProvider>
    );
}
