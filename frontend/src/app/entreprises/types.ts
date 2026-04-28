export type EntrepriseDetailsTab = "infos" | "avis" | "appels" | "osint";

export type PhoneAvailabilityFilter = "" | "true" | "false";

export type EntrepriseCallStats = {
  total: number;
  by_status: Record<string, number>;
};

export type ImportProgressCounters = {
  imported: number;
  skippedWebsite: number;
  skippedInvalid: number;
  skippedDuplicates: number;
};

