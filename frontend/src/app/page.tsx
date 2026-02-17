import React from "react";
import { redirect } from "next/navigation";

/**
 * Page racine: redirige directement vers le dashboard.
 * Pas de comptes / login: accès immédiat aux fonctionnalités.
 */
const HomePage = () => {
  redirect("/dashboard");
};

export default HomePage;

