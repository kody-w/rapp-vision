export const scenarios = Object.freeze({
  matching: {
    label: "Matching peptide",
    display: "MHC I + the clone's matching peptide",
    activated: true,
    mhc: "I",
    matches: true,
  },
  different: {
    label: "Different peptide",
    display: "MHC I + a different peptide",
    activated: true,
    mhc: "I",
    matches: false,
  },
  "class-two": {
    label: "Wrong MHC class",
    display: "MHC II is not this CD8 clone's restriction",
    activated: true,
    mhc: "II",
    matches: true,
  },
  inactive: {
    label: "Not activated",
    display: "Matching peptide-MHC I; no activated effector",
    activated: false,
    mhc: "I",
    matches: true,
  },
});

export function initialState() {
  return {
    scenario: "matching",
    targetStatus: "intact",
    acceptedCount: 0,
    rejectedCount: 0,
    lastAccepted: null,
    decision: "ready",
    message: "Try an encounter. This model follows one CD8 T-cell clone.",
  };
}

export function selectScenario(state, scenario) {
  if (!Object.hasOwn(scenarios, scenario)) throw new RangeError("Unknown encounter scenario.");
  return {
    ...state,
    scenario,
    targetStatus: "intact",
    decision: "ready",
    message: "New encounter selected. The previous accepted receipt is retained.",
  };
}

function reject(state, message) {
  return {
    ...state,
    rejectedCount: state.rejectedCount + 1,
    decision: "rejected",
    message,
  };
}

export function applyAction(state, action) {
  if (action === "reset") return initialState();
  if (action === "antibody") {
    return reject(state, "Rejected: B-cell-derived plasma cells make antibodies. This T cell does not. Accepted state is unchanged.");
  }
  if (action !== "signal") throw new RangeError("Unknown model action.");
  const encounter = scenarios[state.scenario];
  if (!encounter) throw new RangeError("The current scenario is invalid.");
  if (encounter.mhc !== "I") {
    return reject(state, "Rejected: this CD8 clone recognizes its peptide with MHC I, not MHC II. Accepted state is unchanged.");
  }
  if (!encounter.matches) {
    return reject(state, "Rejected: the displayed peptide is not this clone's matching target. Accepted state is unchanged.");
  }
  if (!encounter.activated) {
    return reject(state, "Rejected: this simplified killing model requires an activated cytotoxic effector. Accepted state is unchanged.");
  }
  if (state.targetStatus === "apoptosis") {
    return reject(state, "Rejected: this encounter already has an accepted death signal. Choose a new encounter or reset.");
  }
  const acceptedCount = state.acceptedCount + 1;
  return {
    ...state,
    targetStatus: "apoptosis",
    acceptedCount,
    lastAccepted: { trial: acceptedCount, scenario: "matching", outcome: "apoptosis" },
    decision: "accepted",
    message: "Accepted in the model: an activated CD8 cell recognizes matching peptide-MHC I and signals controlled target-cell death.",
  };
}
