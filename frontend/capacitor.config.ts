/// <reference types="@capacitor/app" />
/// <reference types="@capacitor/keyboard" />

import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'com.agenthub.app',
  appName: 'AgentHub',
  webDir: 'dist',
  plugins: {
    App: {
      disableBackButtonHandler: true,
    },
    Keyboard: {
      resize: 'body',
    },
  },
};

export default config;
