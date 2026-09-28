import React from 'react';
import layout from '@splunk/react-page/18';
import { SplunkThemeProvider } from '@splunk/themes';
import { defaultTheme, getThemeOptions } from '@splunk/splunk-utils/themes';
import Button from '@splunk/react-ui/Button';
import Heading from '@splunk/react-ui/Heading';
import ColumnLayout from '@splunk/react-ui/ColumnLayout';

const theme = getThemeOptions(defaultTheme() || 'enterprise');

layout(
    <SplunkThemeProvider {...theme}>
        <ColumnLayout>
            <ColumnLayout.Row>
                <ColumnLayout.Column>
                    <Heading level={1}>Example page</Heading>
                    <Button appearance="primary" label="Save" />
                </ColumnLayout.Column>
            </ColumnLayout.Row>
        </ColumnLayout>
    </SplunkThemeProvider>,
    { pageTitle: 'Example', hideFooter: true, layout: 'fixed' }
);
