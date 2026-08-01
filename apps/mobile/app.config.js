module.exports = ({ config }) => {
  const apiBaseUrl = process.env.EXITGUIDE_API_BASE_URL?.trim();
  const disableRuntimeConfig = process.env.EXITGUIDE_DISABLE_RUNTIME_CONFIG === "1";

  return {
    ...config,
    extra: {
      ...config.extra,
      ...(apiBaseUrl ? { apiBaseUrl } : {}),
      ...(disableRuntimeConfig ? { runtimeConfigUrl: "" } : {}),
    },
  };
};
