#!/usr/bin/env python

from botocore.credentials import RefreshableCredentials
from botocore.session import get_session
from boto3 import Session
import argparse
import random



def parse_arguments():
    parser = argparse.ArgumentParser(description='Product Creation/Updation')
    parser.add_argument('--role_arn', '-ra', help='Role Arn used for accessing AWS resources', required=True)
    parser.add_argument('--product_version','-pv',help="The version of product to be created. it should be inform vX.X.X  (ex v1.2.1).", required=True)
    parser.add_argument('--version_desc','-vd',help="description of version that is going to be created", required=True)
    args = parser.parse_args()
    return args

def assumed_temp_session(role_arn,session_name):
    session = Session()
    def refresh():
        credentials = session.client('sts').assume_role(RoleArn=role_arn,RoleSessionName=session_name)['Credentials']
        return dict(
            access_key=credentials['AccessKeyId'],
            secret_key=credentials['SecretAccessKey'],
            token=credentials['SessionToken'],
            # Silly that we basically stringify so it can be parsed again
            expiry_time=credentials['Expiration'].isoformat())

    session_credentials = RefreshableCredentials.create_from_metadata(metadata=refresh(),refresh_using=refresh,method='sts-assume-role')
    s = get_session()
    s._credentials = session_credentials
    region = session._session.get_config_variable('region') or 'us-east-1'
    s.set_config_variable('region', region)
    return (Session(botocore_session=s),region)

def create_connection():
    if ROLE_ARN:
        session = assumed_temp_session(ROLE_ARN, "{0}-{1}".format(ROLE_ARN.split("/")[1],random.randrange(0, 99999999)))[0]
        region= assumed_temp_session(ROLE_ARN, "{0}-{1}".format(ROLE_ARN.split("/")[1],random.randrange(0, 99999999)))[1]
        client = session.client('servicecatalog')
    return (client,region)



def create_product(client,product_name, temp_s3_url,region):
    response = client.create_product(Name=product_name,Owner="flux7",Description="ecs-wrokshop",Distributor="flux7",SupportDescription="to enhance the code pipeline to use the service catalog",
        SupportEmail=SUPPORT_EMAIL,
        SupportUrl=SUPPORT_URL,
        ProductType='CLOUD_FORMATION_TEMPLATE',
        ProvisioningArtifactParameters={
            'Name': ARGS.product_version,
            'Description': 'initial version',
            'Info': {
                'LoadTemplateFromURL': temp_s3_url
            },
            'Type': 'CLOUD_FORMATION_TEMPLATE'
        },
        #IdempotencyToken=product_name
    )
    if  response['ProductViewDetail']['Status'] == 'CREATED':
        print "product creation successful "


    product_id = response['ProductViewDetail']['ProductViewSummary']['ProductId']
    product_version_id = response['ProvisioningArtifactDetail']['Id']
    product_version_name = response['ProvisioningArtifactDetail']['Name']
    return (product_id,product_version_id,product_version_name)


def create_version_of_product(client,version,ver_desc, temp_s3_url,product_id,product_name,region):
    response = client.create_provisioning_artifact(ProductId=product_id,
        Parameters={
            'Name': version,
            'Description': ver_desc,
            'Info': {
                'LoadTemplateFromURL': temp_s3_url
            },
            'Type': 'CLOUD_FORMATION_TEMPLATE'
        },
        #IdempotencyToken=version
    )

    print "new version  {} created for product {} in region {}".format(version,product_name,region)




def create_portfolio(client,portfolio_name,region):
    response = client.create_portfolio(
        DisplayName=portfolio_name,
        Description="for the ecs-workshop",
        ProviderName="flux7",
        #IdempotencyToken=portfolio_name
    )
    portfolio_id= response['PortfolioDetail']['Id']
    print "portfolio {} created in region {}".format(portfolio_name,region)
    return portfolio_id

def attach_product_to_portfolio(client,product_id,portfolio_id):
    response = client.associate_product_with_portfolio(
        ProductId=product_id,
        PortfolioId=portfolio_id,
    )

def associate_role_with_portfolio(client,portfolio_id):
    response = client.associate_principal_with_portfolio(
        PortfolioId=portfolio_id,
        PrincipalARN=ROLE_ARN,
        PrincipalType='IAM'
    )
    print "role arn {} is associated with portfolio {}".format(ROLE_ARN,portfolio_id)



def  main(temp_s3_url,product_name_list):
    ser_cat_clt_conn = create_connection()[0]
    region = create_connection()[1]

    """To create portfolio
    """
    portfolio_dict = ser_cat_clt_conn.list_portfolios(PageSize=20)
    if portfolio_dict['PortfolioDetails']==[]:
        print "creating portfolio {} in region {}".format(PORTFOLIO_NAME,region)
        portfolio_id = create_portfolio(ser_cat_clt_conn,PORTFOLIO_NAME,region)
    elif portfolio_dict['PortfolioDetails'] != []:
        for  portfolio in portfolio_dict['PortfolioDetails']:
            if portfolio['DisplayName']==PORTFOLIO_NAME:
                print "portfolio {} already exist in region {}".format(PORTFOLIO_NAME,region)
                portfolio_id = portfolio['Id']
                break
        else:
            print "creating portfolio {} in region {}".format(PORTFOLIO_NAME,region)
            portfolio_id = create_portfolio(ser_cat_clt_conn,PORTFOLIO_NAME,region)



    """TO create product
    """
    response = ser_cat_clt_conn.search_products()

    for product in response['ProductViewSummaries']:
        if product['Name'] == product_name_list[0]:
            product_id =  product['ProductId']
            version_response = ser_cat_clt_conn.describe_product(Id=product_id)
            for version in version_response['ProvisioningArtifacts']:
                if ARGS.product_version == version['Name']:
                    print "product {} with version {}   already exist in region {} and attached with portfolio {}".format(product_name_list[0],ARGS.product_version,region,PORTFOLIO_NAME)
                    break
            else:
                """To create New  Version of  existing product"""
                create_version_of_product(ser_cat_clt_conn,ARGS.product_version,ARGS.version_desc,temp_s3_url,product_id,product_name_list[0],region)
            break

    else:
        product_id,product_version_id,product_version_name =create_product(ser_cat_clt_conn,product_name_list[0],temp_s3_url,region)
        print "product {} created in region {} with version {}".format(product_name_list[0],region,product_version_name)
        """TO associate role with portfolio
        """
        attach_product_to_portfolio(ser_cat_clt_conn,product_id,portfolio_id)
        print "product {} attached with portfolio {}".format(product_name_list[0],PORTFOLIO_NAME)




if __name__ == "__main__":
    ARGS = parse_arguments()
    SUPPORT_EMAIL = "mohit@flux7.com"
    BUCKET_NAME = "platform-test-devops-us-west-2"
    BUCKET_PATH = "ecs-workshop"
    PORTFOLIO_NAME = "ecs-workshop"
    product_name_list = ["common"]
    ROLE_ARN = ARGS.role_arn
    SUPPORT_URL ='https://www.flux7.com'
    temp_s3_url = "https://s3.amazonaws.com/{}/{}/microservice.yml".format(BUCKET_NAME,BUCKET_PATH)
    main(temp_s3_url,product_name_list)
