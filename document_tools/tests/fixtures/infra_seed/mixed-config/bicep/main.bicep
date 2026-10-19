resource plan 'Microsoft.Web/serverfarms@2023-01-01' = {
  name: 'plan'
}

resource site 'Microsoft.Web/sites@2023-01-01' = {
  name: 'site'
  properties: {
    serverFarmId: plan.id
    vault: vault.id
  }
}

resource vault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: 'vault'
}

resource odd 'Microsoft.Contoso/widgets@2023-01-01' = {
  name: 'odd'
}
