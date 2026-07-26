targetScope = 'resourceGroup'

@description('Azure region for all resources.')
param location string = resourceGroup().location

@description('Container Registry name.')
param acrName string

@description('Key Vault name.')
param keyVaultName string

@description('Log Analytics workspace name.')
param logAnalyticsName string

@description('Container Apps environment name.')
param containerAppsEnvironmentName string

@description('Container App name.')
param containerAppName string

@description('Image repository name inside ACR.')
param imageName string = 'offchain-trading-bot'

@description('Image tag to deploy.')
param imageTag string = 'latest'

@description('Trading mode. Use paper or demo for simulation; live for production.')
@allowed([
  'paper'
  'demo'
  'live'
])
param tradingMode string = 'paper'

@description('Market backend. ccxt supports CEX data and live execution; web3 is read-only oracle monitoring.')
@allowed([
  'ccxt'
  'web3'
])
param marketBackend string = 'ccxt'

@description('RPC URL for the Web3 backend.')
@secure()
param rpcUrl string = ''

@description('Exchange API key for ccxt live trading.')
@secure()
param exchangeApiKey string = ''

@description('Exchange API secret for ccxt live trading.')
@secure()
param exchangeApiSecret string = ''

@description('Exchange API password or passphrase for exchanges that require one.')
@secure()
param exchangeApiPassword string = ''

@description('Wallet private key for DEX or Web3 execution workflows.')
@secure()
param walletPrivateKey string = ''

@description('Trading symbol, such as ETH/USDT.')
param symbol string = 'ETH/USDT'

@description('Oracle address for the Web3 market backend.')
param oracleAddress string = ''

@description('Base URL for the REST or CEX API, if required by your deployment pattern.')
param apiBaseUrl string = ''

@description('Exchange identifier used by ccxt, for example binance or kraken.')
param exchangeId string = 'binance'

@description('Container CPU allocation.')
param cpu float = 0.5

@description('Container memory allocation in GiB.')
param memory string = '1.0Gi'

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: logAnalyticsName
  location: location
  properties: {
    retentionInDays: 30
    features: {
      searchVersion: 1
    }
    sku: {
      name: 'PerGB2018'
    }
  }
}

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: acrName
  location: location
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: false
    policies: {
      quarantinePolicy: {
        status: 'disabled'
      }
      trustPolicy: {
        type: 'Notary'
        status: 'disabled'
      }
      retentionPolicy: {
        days: 7
        status: 'enabled'
      }
    }
  }
}

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: keyVaultName
  location: location
  properties: {
    tenantId: subscription().tenantId
    sku: {
      family: 'A'
      name: 'standard'
    }
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
    enablePurgeProtection: true
    publicNetworkAccess: 'Enabled'
    networkAcls: {
      defaultAction: 'Allow'
      bypass: 'AzureServices'
    }
  }
}

resource rpcSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = if (!empty(rpcUrl)) {
  name: '${keyVault.name}/rpc-url'
  properties: {
    value: rpcUrl
  }
}

resource exchangeApiKeySecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = if (!empty(exchangeApiKey)) {
  name: '${keyVault.name}/exchange-api-key'
  properties: {
    value: exchangeApiKey
  }
}

resource exchangeApiSecretSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = if (!empty(exchangeApiSecret)) {
  name: '${keyVault.name}/exchange-api-secret'
  properties: {
    value: exchangeApiSecret
  }
}

resource exchangeApiPasswordSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = if (!empty(exchangeApiPassword)) {
  name: '${keyVault.name}/exchange-api-password'
  properties: {
    value: exchangeApiPassword
  }
}

resource walletPrivateKeySecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = if (!empty(walletPrivateKey)) {
  name: '${keyVault.name}/wallet-private-key'
  properties: {
    value: walletPrivateKey
  }
}

resource containerEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: containerAppsEnvironmentName
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
  }
}

resource containerApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: containerAppName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    managedEnvironmentId: containerEnv.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: false
        targetPort: 8000
        transport: 'auto'
      }
      registries: [
        {
          server: acr.properties.loginServer
          identity: 'system'
        }
      ]
      secrets: [
        {
          name: 'rpc-url'
          keyVaultUrl: '${keyVault.properties.vaultUri}secrets/rpc-url'
          identity: 'system'
        }
        {
          name: 'exchange-api-key'
          keyVaultUrl: '${keyVault.properties.vaultUri}secrets/exchange-api-key'
          identity: 'system'
        }
        {
          name: 'exchange-api-secret'
          keyVaultUrl: '${keyVault.properties.vaultUri}secrets/exchange-api-secret'
          identity: 'system'
        }
        {
          name: 'exchange-api-password'
          keyVaultUrl: '${keyVault.properties.vaultUri}secrets/exchange-api-password'
          identity: 'system'
        }
        {
          name: 'wallet-private-key'
          keyVaultUrl: '${keyVault.properties.vaultUri}secrets/wallet-private-key'
          identity: 'system'
        }
      ]
    }
    template: {
      revisionSuffix: imageTag
      containers: [
        {
          name: 'offchain-bot'
          image: '${acr.properties.loginServer}/${imageName}:${imageTag}'
          env: [
            {
              name: 'OFFCHAIN_TRADING_MODE'
              value: tradingMode
            }
            {
              name: 'OFFCHAIN_MARKET_BACKEND'
              value: marketBackend
            }
            {
              name: 'OFFCHAIN_SYMBOL'
              value: symbol
            }
            {
              name: 'OFFCHAIN_EXCHANGE_ID'
              value: exchangeId
            }
            {
              name: 'OFFCHAIN_API_BASE_URL'
              value: apiBaseUrl
            }
            {
              name: 'OFFCHAIN_RPC_URL'
              secretRef: 'rpc-url'
            }
            {
              name: 'OFFCHAIN_EXCHANGE_API_KEY'
              secretRef: 'exchange-api-key'
            }
            {
              name: 'OFFCHAIN_EXCHANGE_API_SECRET'
              secretRef: 'exchange-api-secret'
            }
            {
              name: 'OFFCHAIN_EXCHANGE_API_PASSWORD'
              secretRef: 'exchange-api-password'
            }
            {
              name: 'OFFCHAIN_WALLET_PRIVATE_KEY'
              secretRef: 'wallet-private-key'
            }
          ]
          resources: {
            cpu: cpu
            memory: memory
          }
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 1
      }
    }
  }
}

resource acrPullRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, containerApp.id, 'acrpull')
  scope: acr
  properties: {
    principalId: containerApp.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')
  }
}

resource keyVaultSecretsRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, containerApp.id, 'kvsecrets')
  scope: keyVault
  properties: {
    principalId: containerApp.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6')
  }
}

output acrLoginServer string = acr.properties.loginServer
output containerAppFqdn string = containerApp.properties.configuration.ingress.fqdn
output keyVaultUri string = keyVault.properties.vaultUri
