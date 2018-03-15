#!/usr/bin/env python

from botocore.credentials import RefreshableCredentials
from botocore.session import get_session
from boto3 import Session
import argparse
import random
import os
import fnmatch
import datetime, time


def parse_arguments():
    parser = argparse.ArgumentParser(description='Product Creation/Updation')
    parser.add_argument('--role_arn', '-ra', help='Role Arn used for accessing AWS resources', required=True)
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
        client_s3 = session.client('s3')
    return (client,region,client_s3)



def create_product(client,product_name, temp_s3_url):
    response = client.create_product(Name=product_name,Owner="flux7",Description="ecs-wrokshop",Distributor="flux7",SupportDescription="to enhance the code pipeline to use the service catalog",
        SupportEmail=SUPPORT_EMAIL,
        SupportUrl=SUPPORT_URL,
        ProductType='CLOUD_FORMATION_TEMPLATE',
        ProvisioningArtifactParameters={
            'Name':  VERSION,
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

def compare_templates(conn,template_utl):
    client_s3 = conn[2]
    object_info_list=template_utl.split("/",4)
    bucket=object_info_list[3]
    key=object_info_list[4]
    print bucket
    print key
    with open('/tmp/temp_template.yml', 'wb') as data:
        client_s3.download_fileobj(bucket,key, data)

    with open('test.yml') as f1, open('test1.yml') as f2:
        difference = set(f1).difference(f2)

    print difference

def get_latest_version_template(ser_cat_clt_conn,latest_version_id,product_id):
    response = ser_cat_clt_conn.describe_provisioning_artifact(ProvisioningArtifactId=latest_version_id,ProductId=product_id)
    print "latest template = {}".format(response['Info']['TemplateUrl'])
    return response['Info']['TemplateUrl']



def portfolio(ser_cat_clt_conn,region):
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

    return portfolio_id

def main(temp_s3_url,product_name,conn):
    ser_cat_clt_conn = conn[0]
    region = conn[1]
    client_s3 = conn[2]

    """TO create product
    """
    response = ser_cat_clt_conn.search_products()

    for product in response['ProductViewSummaries']:
        if product['Name'] == product_name:
            product_id =  product['ProductId']
            version_response = ser_cat_clt_conn.describe_product(Id=product_id)
            tdict= {}
            vdict= {}
            for version in  version_response['ProvisioningArtifacts']:
                tdict[time.mktime(version['CreatedTime'].timetuple())]=version['Id']
                vdict[time.mktime(version['CreatedTime'].timetuple())]=version['Name']

            latest_version_id= tdict[max(tdict.keys())]
            latest_version_name= vdict[max(vdict.keys())]
            print latest_version_id
            print latest_version_name
            template_utl = get_latest_version_template(ser_cat_clt_conn,latest_version_id,product_id)
            print template_utl
            compare_templates(conn,template_utl)
            """
            for version in version_response['ProvisioningArtifacts']:
                if "v1.0.0" == version['Name']:
                    print "product {} with version {}   already exist in region {} and attached with portfolio {}".format(product_name,"v1.0.0",region,PORTFOLIO_NAME)
                    break
            else:
                #To create New  Version of  existing product
                create_version_of_product(ser_cat_clt_conn,"v1.0.0",ARGS.version_desc,temp_s3_url,product_id,product_name,region)
            break

    else:
        product_id,product_version_id,product_version_name =create_product(ser_cat_clt_conn,product_name,temp_s3_url)
        print "product {} created in region {} with version {}".format(product_name,region,product_version_name)
        #TO associate role with portfolio
        attach_product_to_portfolio(ser_cat_clt_conn,product_id,portfolio_id)
        print "product {} attached with portfolio {}".format(product_name,PORTFOLIO_NAME)

    """



if __name__ == "__main__":
    ARGS = parse_arguments()
    SUPPORT_EMAIL = "mohit@flux7.com"
    BUCKET_NAME = "platform-test-devops-us-west-2"
    BUCKET_PATH = "ecs-workshop"
    PORTFOLIO_NAME = "ecs-workshop"
    product_name_list=os.listdir('../cf-templates')
    print product_name_list
    ROLE_ARN = ARGS.role_arn
    SUPPORT_URL ='https://www.flux7.com'
    VERSION = 1.0
    conn = create_connection()
    ser_cat_clt_conn = conn[0]
    region = conn[1]
    client_s3 = conn[2]

    portfolio(ser_cat_clt_conn,region)

    for product_name in product_name_list:
        product_template=fnmatch.filter(os.listdir('../cf-templates/{}'.format(product_name)), '*.yml')[0]
        product_temp_s3_url='{}/{}/{}'.format(client_s3.meta.endpoint_url,BUCKET_NAME,"{}/cf-templates/{}/{}".format(BUCKET_PATH,product_name,product_template))
        print "product_name={}".format(product_name)
        print "product template name={}/{}\n".format(product_name,product_template)
        main(product_temp_s3_url,product_name,conn)